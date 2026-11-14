#include "h25_r1_hook.h"
int main(int argc, char** argv) {
  if(argc != 5)return 2;
  // Synthetic fixture covers baseline control, mutation, and exact counts.
  if (!h25_r1::target_leaf(0))return 3;
  h25_r1::check_row(0,0,1,2);
  if(h25_r1::replacement(0,0,1)!=3)return 4;
  if(h25_r1::replacement(0,0,2)!=2)return 5;
  h25_r1::verify();
  return 0;
}
