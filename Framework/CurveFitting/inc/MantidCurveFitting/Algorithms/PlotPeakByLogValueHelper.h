// Mantid Repository : https://github.com/mantidproject/mantid
//
// Copyright &copy; 2008 ISIS Rutherford Appleton Laboratory UKRI,
//     NScD Oak Ridge National Laboratory, European Spallation Source
//     & Institut Laue - Langevin
// SPDX - License - Identifier: GPL - 3.0 +
#ifndef MANTID_CURVEFITTING_PLOTPEAKBULOGVALUEHELPER_H_
#define MANTID_CURVEFITTING_PLOTPEAKBULOGVALUEHELPER_H_

#include "MantidAPI/IAlgorithm_fwd.h"
#include "MantidAPI/MatrixWorkspace_fwd.h"

#include <string>
#include <vector>

namespace Mantid {
namespace CurveFitting {
namespace Algorithms {

struct InputData {
  /// Constructor
  InputData(const std::string &nam, int ix, int s, int p, double st = 0,
            double en = 0)
      : name(nam), i(ix), spec(s), period(p), start(st), end(en) {}
  /// Copy constructor
  InputData(const InputData &data)
      : name(data.name), i(data.i), spec(data.spec), period(data.period),
        start(data.start), end(data.end), ws(data.ws) {
    indx.assign(data.indx.begin(), data.indx.end());
  }
  std::string name; ///< Name of a workspace or file
  int i;            ///< Workspace index of the spectra to fit
  int spec;         ///< Spectrum number to fit
  int period;       ///< Period, needed if a file contains several periods
  double start;     ///< starting axis value
  double end;       ///< ending axis value
  API::MatrixWorkspace_sptr ws; ///< shared pointer to the workspace
  std::vector<int> indx; ///< a list of ws indices to fit if i and spec < 0
};
/// Get a workspace
InputData getWorkspace(const InputData &data, API::IAlgorithm_sptr load);

/// Create a list of input workspace names
std::vector<InputData> makeNames(std::string inputList, int default_wi,
                                 int default_spec);

} // namespace Algorithms
} // namespace CurveFitting
} // namespace Mantid

#endif /*MANTID_CURVEFITTING_PLOTPEAKBULOGVALUEHELPER_H_*/
