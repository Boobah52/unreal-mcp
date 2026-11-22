#pragma once

// Standalone byte-level newline-delimited JSON framing shared with the native
// Unreal TCP receiver. Standard C++ only, so this exact header can be compiled
// and tested on CI runners without Unreal Engine installed.
//
// Contract: one compact JSON request followed by LF; CRLF also accepted.
// A TCP recv() is an arbitrary chunk, not a complete request.
// Maximum frame length is bounded; embedded NUL and empty frames are rejected.
// JSON syntax is validated separately by Unreal's FJsonSerializer.
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

class FMCPJsonLineFramer final
{
public:
    explicit FMCPJsonLineFramer(std::size_t InMaxFrameBytes = 1024U * 1024U)
        : MaxFrameBytes(InMaxFrameBytes)
    {
    }

    bool Consume(const std::uint8_t* Data, std::size_t Length,
                 std::vector<std::string>& CompletedFrames)
    {
        if (Data == nullptr && Length != 0)
        {
            return false;
        }

        for (std::size_t Index = 0; Index < Length; ++Index)
        {
            const unsigned char Current = Data[Index];
            if (Current == 0)
            {
                return false;  // Never pass embedded NUL to FString conversion.
            }
            if (Current == '\n')
            {
                if (!Pending.empty() && Pending.back() == '\r')
                {
                    Pending.pop_back();
                }
                if (Pending.empty() || Pending.size() > MaxFrameBytes)
                {
                    return false;
                }
                CompletedFrames.push_back(Pending);
                Pending.clear();
                continue;
            }

            // Permit one extra CR only for CRLF at the configured limit.
            if (Pending.size() >= MaxFrameBytes && Current != '\r')
            {
                return false;
            }
            if (Pending.size() > MaxFrameBytes)
            {
                return false;
            }
            Pending.push_back(static_cast<char>(Current));
        }
        return true;
    }

private:
    std::size_t MaxFrameBytes;
    std::string Pending;
};
