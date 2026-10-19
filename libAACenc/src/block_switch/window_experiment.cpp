#include "window_experiment.h"
#include "FDK_tools_rom.h"

namespace {
int mode = WINDOW_NATIVE_DEFAULT, frame = -1;
FDK_WINDOW_OBSERVER observer = 0;
void *context = 0;
// Native sequence numbering is LONG=0, START=1, SHORT=2, STOP=3.
const int shapes[4][4] = {{0, 0, 0, 0}, {1, 1, 1, 1},
                         {0, 0, 1, 0}, {1, 1, 0, 1}};
}
extern "C" int FDKwindowExperimentConfigure(int requested_mode, FDK_WINDOW_OBSERVER fn, void *data) {
  if (requested_mode < -1 || requested_mode > 3) return -1;
  mode = requested_mode; observer = fn; context = data; frame = -1;
  return 0;
}
extern "C" int FDKwindowExperimentShape(int sequence, int native_shape) {
  if (mode < 0 || sequence < 0 || sequence > 3) return native_shape;
  return shapes[mode][sequence];
}
extern "C" void FDKwindowExperimentObserve(int channel, int sequence, int shape,
                                           int previous_shape, int length,
                                           int previous_right_length, const FIXP_WTP *previous_right) {
  if (!observer) return;
  if (channel == 0) ++frame;
  FDK_WINDOW_EVENT e = {};
  e.frame_index = frame; e.channel = channel; e.sequence = sequence;
  e.shape = shape; e.previous_shape = previous_shape; e.mode = mode;
  e.right_shape = shape;
  e.right_length = (sequence == 1 || sequence == 2) ? length / 8 : length;
  e.bootstrap = previous_right_length == 0;
  e.left_length = e.bootstrap ? e.right_length : previous_right_length;
  e.left_shape = e.bootstrap ? shape :
      (previous_right == FDKgetWindowSlope(e.left_length, 0) ? 0 :
       previous_right == FDKgetWindowSlope(e.left_length, 1) ? 1 : -1);
  observer(&e, context);
}
