#include "MCPServerRunnable.h"
#include "MCPJsonLineFramer.h"
#include "Containers/StringConv.h"
#include <string>
#include <vector>
#include "UnrealMCPBridge.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Interfaces/IPv4/IPv4Address.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "JsonObjectConverter.h"
#include "Misc/ScopeLock.h"
#include "HAL/PlatformTime.h"

// Buffer size for receiving data
const int32 BufferSize = 8192;

FMCPServerRunnable::FMCPServerRunnable(UUnrealMCPBridge* InBridge, TSharedPtr<FSocket> InListenerSocket)
    : Bridge(InBridge)
    , ListenerSocket(InListenerSocket)
    , bRunning(true)
{
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Created server runnable"));
}

FMCPServerRunnable::~FMCPServerRunnable()
{
    // Note: We don't delete the sockets here as they're owned by the bridge
}

bool FMCPServerRunnable::Init()
{
    return true;
}

namespace
{
    // FSocket::Send may write fewer bytes than requested; the byte count, not
    // FString::Len(), governs progress over the UTF-8 wire representation.
    bool SendMCPReply(FSocket* Socket, const FString& Json)
    {
        if (Socket == nullptr)
        {
            return false;
        }

        const FString Framed = Json + TEXT("\n");
        FTCHARToUTF8 Utf8(*Framed);
        const uint8* Bytes = reinterpret_cast<const uint8*>(Utf8.Get());
        const int32 Total = Utf8.Length();
        int32 Offset = 0;
        const double Deadline = FPlatformTime::Seconds() + 5.0;

        while (Offset < Total && FPlatformTime::Seconds() < Deadline)
        {
            int32 BytesSent = 0;
            if (Socket->Send(Bytes + Offset, Total - Offset, BytesSent) && BytesSent > 0)
            {
                Offset += BytesSent;
                continue;
            }

            const int32 LastError = static_cast<int32>(
                ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->GetLastErrorCode());
            if (LastError != SE_EWOULDBLOCK && LastError != SE_EINTR)
            {
                return false;
            }
            FPlatformProcess::Sleep(0.005f);
        }
        return Offset == Total;
    }
}

// Protocol: one newline-terminated JSON request per TCP connection.
// A TCP recv is NOT a message boundary (see Epic FSocket::Recv documentation).
uint32 FMCPServerRunnable::Run()
{
    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Started (JSON lines, one request per connection)"));

    while (bRunning)
    {
        if (!ListenerSocket.IsValid())
        {
            break;
        }

        bool bPending = false;
        if (ListenerSocket->HasPendingConnection(bPending) && bPending)
        {
            ClientSocket = MakeShareable(ListenerSocket->Accept(TEXT("MCPClient")));
            if (!ClientSocket.IsValid())
            {
                UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Accept failed"));
                continue;
            }

            ClientSocket->SetNoDelay(true);
            ClientSocket->SetNonBlocking(true);
            FMCPJsonLineFramer Framer(1024U * 1024U);
            bool bRequestComplete = false;
            double LastDataAt = FPlatformTime::Seconds();

            while (bRunning && !bRequestComplete)
            {
                uint8 Buffer[8192];
                int32 BytesRead = 0;
                const bool bReceived = ClientSocket->Recv(Buffer, sizeof(Buffer), BytesRead);
                if (bReceived && BytesRead > 0)
                {
                    LastDataAt = FPlatformTime::Seconds();
                    std::vector<std::string> CompleteRequests;
                    if (!Framer.Consume(Buffer, static_cast<std::size_t>(BytesRead), CompleteRequests))
                    {
                        SendMCPReply(ClientSocket.Get(), TEXT("{\"status\":\"error\",\"error\":\"invalid_or_oversized_request\"}"));
                        break;
                    }

                    if (!CompleteRequests.empty())
                    {
                        bRequestComplete = true;
                        // The Python client opens a fresh socket per command.
                        // Reject pipelined commands rather than silently dropping any.
                        if (CompleteRequests.size() != 1 || Framer.HasBufferedBytes())
                        {
                            SendMCPReply(ClientSocket.Get(), TEXT("{\"status\":\"error\",\"error\":\"one_request_per_connection\"}"));
                            break;
                        }

                        const std::string& RequestBytes = CompleteRequests[0];
                        // Convert ONLY after the complete UTF-8 line is assembled.
                        // No out-of-bounds NUL terminator is written to Buffer.
                        FUTF8ToTCHAR Converted(RequestBytes.data(), static_cast<int32>(RequestBytes.size()));
                        const FString ReceivedText(Converted.Length(), Converted.Get());

                        TSharedPtr<FJsonObject> JsonObject;
                        TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ReceivedText);
                        if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
                        {
                            SendMCPReply(ClientSocket.Get(), TEXT("{\"status\":\"error\",\"error\":\"invalid_json\"}"));
                            break;
                        }

                        FString CommandType;
                        if (!JsonObject->TryGetStringField(TEXT("command"), CommandType) || CommandType.IsEmpty())
                        {
                            SendMCPReply(ClientSocket.Get(), TEXT("{\"status\":\"error\",\"error\":\"missing_command\"}"));
                            break;
                        }

                        TSharedPtr<FJsonObject> Params = MakeShared<FJsonObject>();
                        if (JsonObject->HasField(TEXT("params")))
                        {
                            TSharedPtr<FJsonValue> ParamValue = JsonObject->TryGetField(TEXT("params"));
                            if (!ParamValue.IsValid() || ParamValue->Type != EJson::Object)
                            {
                                SendMCPReply(ClientSocket.Get(), TEXT("{\"status\":\"error\",\"error\":\"invalid_params\"}"));
                                break;
                            }
                            Params = ParamValue->AsObject();
                        }

                        const FString Reply = Bridge->ExecuteCommand(CommandType, Params);
                        if (!SendMCPReply(ClientSocket.Get(), Reply))
                        {
                            UE_LOG(LogTemp, Error, TEXT("MCPServerRunnable: Could not fully send response"));
                        }
                    }
                }
                else if (!bReceived)
                {
                    const int32 LastError = static_cast<int32>(
                        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->GetLastErrorCode());
                    if (LastError != SE_EWOULDBLOCK && LastError != SE_EINTR)
                    {
                        break;
                    }
                }

                if (FPlatformTime::Seconds() - LastDataAt > 10.0)
                {
                    UE_LOG(LogTemp, Warning, TEXT("MCPServerRunnable: Idle request timeout"));
                    break;
                }
                FPlatformProcess::Sleep(0.005f);
            }

            ClientSocket->Close();
            ClientSocket.Reset();
        }
        FPlatformProcess::Sleep(0.01f);
    }

    UE_LOG(LogTemp, Display, TEXT("MCPServerRunnable: Stopped"));
    return 0;
}

void FMCPServerRunnable::Stop()
{
    bRunning = false;
}

void FMCPServerRunnable::Exit()
{
}

