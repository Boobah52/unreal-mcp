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
    std::cout << "native line-framing tests passed" << std::endl;
    return 0;
}
