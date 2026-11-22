#include "MCPJsonLineFramer.h"

#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
#include <iostream>

int main() {
    using std::string;
    using std::vector;
    {
        FMCPJsonLineFramer framer(1024);
        vector<string> frames;
        string payload = R"({"command":"create_blueprint","params":{"name":"café 🐝"}})" "\n";
        for (unsigned char byte : payload) {
            assert(framer.Consume(&byte, 1, frames));
        }
        assert(frames.size() == 1);
        assert(frames[0] == payload.substr(0, payload.size()-1));
    }
    {
        FMCPJsonLineFramer framer(1024);
        vector<string> frames;
        string data = "{\"command\":\"one\"}\r\n{\"command\":\"two\"}\n";
        assert(framer.Consume(reinterpret_cast<const std::uint8_t*>(data.data()), data.size(), frames));
        assert(frames.size() == 2);
        assert(frames[0] == "{\"command\":\"one\"}");
        assert(frames[1] == "{\"command\":\"two\"}");
    }
    {
        FMCPJsonLineFramer framer(8);
        vector<string> frames;
        string too_long = "123456789\n";
        assert(!framer.Consume(reinterpret_cast<const std::uint8_t*>(too_long.data()), too_long.size(), frames));
        assert(frames.empty());
    }
    {
        FMCPJsonLineFramer framer(8192);
        vector<string> frames;
        string long_json = "{\"payload\":\"" + string(4096, 'z') + "\"}\n";
        assert(framer.Consume(reinterpret_cast<const std::uint8_t*>(long_json.data()), 17, frames));
        assert(frames.empty());
        assert(framer.Consume(reinterpret_cast<const std::uint8_t*>(long_json.data()+17), long_json.size()-17, frames));
        assert(frames.size() == 1);
        assert(frames[0] == long_json.substr(0, long_json.size()-1));
    }
    {
        FMCPJsonLineFramer framer(32);
        vector<string> frames;
        const string empty = "\n";
        assert(!framer.Consume(reinterpret_cast<const std::uint8_t*>(empty.data()), empty.size(), frames));
    }
    {
        // Exercise every possible contiguous TCP chunk size for a UTF-8
        // multibyte document; byte segmentation must not change the result.
        const string request = R"({"command":"echo","name":"café 🐝","value":"a\nb"})" "\n";
        for (std::size_t chunkSize = 1; chunkSize <= request.size(); ++chunkSize) {
            FMCPJsonLineFramer framer(4096);
            vector<string> frames;
            for (std::size_t offset = 0; offset < request.size();) {
                const std::size_t remaining = request.size() - offset;
                const std::size_t amount = (chunkSize < remaining) ? chunkSize : remaining;
                assert(framer.Consume(
                    reinterpret_cast<const std::uint8_t*>(request.data() + offset),
                    amount, frames));
                offset += amount;
            }
            assert(frames.size() == 1);
            assert(frames[0] == request.substr(0, request.size()-1));
            assert(!framer.HasBufferedBytes());
        }
    }
    {
        // Boundaries are in bytes, not Unicode code points.
        FMCPJsonLineFramer framer(8);
        vector<string> frames;
        const string exactlyAtLimit = "12345678\r\n";
        assert(framer.Consume(
            reinterpret_cast<const std::uint8_t*>(exactlyAtLimit.data()),
            exactlyAtLimit.size(), frames));
        assert(frames.size() == 1 && frames[0] == "12345678");
    }
    {
        FMCPJsonLineFramer framer(80);
        vector<string> frames;
        const string withNul("hi\0bye\n", 7);
        assert(!framer.Consume(
            reinterpret_cast<const std::uint8_t*>(withNul.data()),
            withNul.size(), frames));
    }
    {
        FMCPJsonLineFramer framer(1024);
        vector<string> frames;
        const string pipelined = "{\"command\":\"one\"}\n{\"command\":\"unfinished\"";
        assert(framer.Consume(
            reinterpret_cast<const std::uint8_t*>(pipelined.data()),
            pipelined.size(), frames));
        assert(frames.size() == 1);
        assert(framer.HasBufferedBytes());
    }
    std::cout << "native line-framing tests passed" << std::endl;
    return 0;
}
