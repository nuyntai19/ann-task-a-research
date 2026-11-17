#pragma once

// Currently unused.
/*
#include <math.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <immintrin.h>
#include <type_traits>
#include <algorithm>
#include <atomic>
#include <functional>
#include <queue>
#include <random>
#include <set>
#include <type_traits>


#if defined(__GNUC__) || defined(__clang__)
#include <cpuid.h>
#endif

#define TMM0    0
#define TMM1    1
#define TMM2    2
#define TMM3    3
#define TMM4    4
#define TMM5    5
#define TMM6    6
#define TMM7    7

// #define TILE_SHAPE 256

#if TILE_SHAPE == 256
#define TILE_M 16
#define TILE_K 64
#define TILE_N 16
#else
#define TILE_M 8
#define TILE_K 32
#define TILE_N 8
#endif

#define MAX 1024

#if TILE_SHAPE == 256
#define MAX_ROWS 16
#define MAX_COLS 64
#define STRIDE 64
#else
#define MAX_ROWS 8
#define MAX_COLS 32
#define STRIDE 32
#endif

#define AMX_ALIGN(x) __attribute__((aligned(x)))

#define ARCH_GET_XCOMP_PERM     0x1022
#define ARCH_REQ_XCOMP_PERM     0x1023
#define XFEATURE_XTILECFG       17
#define XFEATURE_XTILEDATA      18

namespace parlayANN {

/* Set_tiledata_use() - Invoke syscall to set ARCH_SET_STATE_USE */
inline bool set_tiledata_use()
{
   if (syscall(SYS_arch_prctl, ARCH_REQ_XCOMP_PERM, XFEATURE_XTILEDATA))
   {
      printf("\n Fail to do XFEATURE_XTILEDATA \n\n");
      return false;
   }
   else
   {
//      printf("\n TILE DATA USE SET - OK \n\n");
      return true;
   }

   return true;
}

thread_local bool set_tdu = false;

//Define tile config data structure
typedef struct __tile_config
{
  uint8_t palette_id;
  uint8_t start_row;
  uint8_t reserved_0[14];
  uint16_t colsb[16];
  uint8_t rows[16];
} __tilecfg;

/* Initialize tile config */
inline void init_tile_config (__tilecfg *tileinfo)
{
  int i;
  tileinfo->palette_id = 1;
  tileinfo->start_row = 0;

  for (i = 0; i < 8; ++i)
  {
    tileinfo->colsb[i] = MAX_COLS;
    tileinfo->rows[i] =  MAX_ROWS;
  }

  _tile_loadconfig (tileinfo);
}

void setup_amx() {
  if (!set_tdu) {
    set_tiledata_use();

    // Load tile configuration
    __tilecfg tile_data = {0};
    init_tile_config (&tile_data);

    set_tdu = true;
  }
}

// Function to check for AMX support
bool check_amx_support() {
    unsigned int eax = 7, ecx = 0;
    unsigned int ebx, edx;
#if defined(__GNUC__) || defined(__clang__)
    // For GCC and Clang, use the __get_cpuid intrinsic
    if (!__get_cpuid(eax, &eax, &ebx, &ecx, &edx)) {
        return false;
    }
#else
    // Fallback for other compilers - may need platform-specific implementation
    return false;
#endif
    // Check for the AMX feature bits in the edx register
    // Bit 22: AMX-BF16
    // Bit 24: AMX-TILE
    // Bit 25: AMX-INT8
    constexpr unsigned int amx_bf16_mask = (1 << 22);
    constexpr unsigned int amx_tile_mask = (1 << 24);
    constexpr unsigned int amx_int8_mask = (1 << 25);
    return (edx & amx_bf16_mask) && (edx & amx_tile_mask) && (edx & amx_int8_mask);
}

// The src matrix is K x N.
// Swizzle to layout column chunks contiguously.
void amx_b_layout_transform(uint8_t *src, uint8_t *dst, /* K */size_t rows_src, /* N */size_t cols_src)
{
  for (int k = 0; k < rows_src/4; k++) {
    for (int i = 0; i < cols_src; i++) {
      for (int j = 0; j < 4; j++) {
        dst[k*cols_src*4 + i*4 + j] = src[k*cols_src*4 + j*cols_src + i];
      }
    }
  }
}

void l1_lower(uint8_t *A, uint8_t *B, int32_t *C, size_t M, size_t N, size_t K) {
  for(int mi=0; mi<(M/TILE_M); mi+=2) {
    for(int ni=0; ni<(N/TILE_N); ni+=2) {
      if (ni > mi) continue;
      _tile_zero(TMM4);
      _tile_zero(TMM5);
      _tile_zero(TMM6);
      _tile_zero(TMM7);
      for(int ki=0; ki<(K/TILE_K); ++ki)
      {
        _tile_loadd(TMM0, A+mi*TILE_M*K+ki*TILE_K, K); // Load A
        _tile_loadd(TMM2, B+ki*(TILE_K/4)*(N*4)+ni*TILE_N*4, N*4); // Load B
        _tile_dpbuud(TMM4, TMM0, TMM2); // C += A * B
        _tile_loadd(TMM1, A+(mi+1)*TILE_M*K+ki*TILE_K, K); // Load A+1
        _tile_dpbuud(TMM6, TMM1, TMM2); // C += A * B
        _tile_loadd(TMM3, B+ki*(TILE_K/4)*(N*4)+(ni+1)*TILE_N*4, N*4); // Load B+1
        _tile_dpbuud(TMM5, TMM0, TMM3); // C += A * B
        _tile_dpbuud(TMM7, TMM1, TMM3); // C += A * B
      }
      _tile_stored(TMM4, (int8_t *)C+mi*TILE_M*N*sizeof(int32_t)+ni*TILE_N*sizeof(int32_t), N*sizeof(int32_t)); // Store C00
      _tile_stored(TMM5, (int8_t *)C+mi*TILE_M*N*sizeof(int32_t)+(ni+1)*TILE_N*sizeof(int32_t), N*sizeof(int32_t)); // Store C01
      _tile_stored(TMM6, (int8_t *)C+(mi+1)*TILE_M*N*sizeof(int32_t)+ni*TILE_N*sizeof(int32_t), N*sizeof(int32_t)); // Store C10
      _tile_stored(TMM7, (int8_t *)C+(mi+1)*TILE_M*N*sizeof(int32_t)+(ni+1)*TILE_N*sizeof(int32_t), N*sizeof(int32_t)); // Store C11
    }
  }
}



}
*/

