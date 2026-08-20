#pragma once

#if __has_include(<node/node_api.h>)
#include <node/node_api.h>
#elif __has_include(<node_api.h>)
#include <node_api.h>
#else
#error "node_api.h was not found; install Node.js development headers"
#endif
