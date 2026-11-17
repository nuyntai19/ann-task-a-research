// R80.4: explicitly include the target PiPNN header (NO historic PCH),
// followed by the ORIGINAL benchmark's main function.
// Exactly the same wrapper is used to build D0 and E with differing -I roots.
#include "PipNN/neighbors.h"
#include "bench/neighborsTime.C"
