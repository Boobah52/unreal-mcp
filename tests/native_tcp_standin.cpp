// Cross-platform native TCP stand-in for contract testing.
// It exercises the EXACT portable framing header used by Unreal's socket
// receiver, but never uses UE headers or claims UE native verification.
#include "MCPJsonLineFramer.h"

#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#if defined(_WIN32)
  #define WIN32_LEAN_AND_MEAN
  #include <winsock2.h>
  #include <ws2tcpip.h>
  using NativeSocket = SOCKET;
  constexpr NativeSocket InvalidSocket = INVALID_SOCKET;
  static void CloseNative(NativeSocket s) { closesocket(s); }
#else
  #include <arpa/inet.h>
  #include <netinet/in.h>
  #include <sys/socket.h>
  #include <unistd.h>
  using NativeSocket = int;
  constexpr NativeSocket InvalidSocket = -1;
  static void CloseNative(NativeSocket s) { close(s); }
#endif

static std::string ToHex(const std::string& data) {
    const char alphabet[] = "0123456789abcdef";
    std::string result;
    result.reserve(data.size() * 2);
    for (unsigned char c : data) {
        result.push_back(alphabet[c >> 4]);
        result.push_back(alphabet[c & 15]);
    }
    return result;
}

static bool SendAll(NativeSocket client, const std::string& data) {
    std::size_t offset = 0;
    while (offset < data.size()) {
        const std::size_t left = data.size() - offset;
        const int amount = static_cast<int>(left > 8192 ? 8192 : left);
        const int written = ::send(client, data.data() + offset, amount, 0);
        if (written <= 0) return false;
        offset += static_cast<std::size_t>(written);
    }
    return true;
}

int main() {
#if defined(_WIN32)
    WSADATA init{};
    if (WSAStartup(MAKEWORD(2, 2), &init) != 0) return 10;
#endif
    NativeSocket listener = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listener == InvalidSocket) return 11;
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(0);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::bind(listener, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) != 0)
        return 12;
    if (::listen(listener, 4) != 0) return 13;
    sockaddr_in bound{};
#if defined(_WIN32)
    int length = sizeof(bound);
#else
    socklen_t length = sizeof(bound);
#endif
    if (::getsockname(listener, reinterpret_cast<sockaddr*>(&bound), &length) != 0)
        return 14;
    std::cout << "READY " << ntohs(bound.sin_port) << std::endl;

    constexpr int ExpectedConnections = 4;
    for (int connection = 0; connection < ExpectedConnections; ++connection) {
        NativeSocket client = ::accept(listener, nullptr, nullptr);
        if (client == InvalidSocket) return 15;
        FMCPJsonLineFramer framer(1024U * 1024U);
        std::vector<std::string> frames;
        bool valid = true;
        while (frames.empty()) {
            std::uint8_t bytes[8192];
            const int read = ::recv(client, reinterpret_cast<char*>(bytes), sizeof(bytes), 0);
            if (read <= 0 || !framer.Consume(bytes, static_cast<std::size_t>(read), frames)) {
                valid = false;
                break;
            }
        }
        if (!valid || frames.size() != 1 || framer.HasBufferedBytes()) {
            SendAll(client, "{\"status\":\"error\",\"error\":\"bad_frame\"}\n");
            CloseNative(client);
            return 16;
        }
        const std::string response =
            "{\"status\":\"ok\",\"hex\":\"" + ToHex(frames.front()) + "\"}\n";
        if (!SendAll(client, response)) {
            CloseNative(client);
            return 17;
        }
        CloseNative(client);
    }
    CloseNative(listener);
#if defined(_WIN32)
    WSACleanup();
#endif
    std::cout << "COMPLETE " << ExpectedConnections << std::endl;
    return 0;
}
