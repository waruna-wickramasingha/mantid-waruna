// Mantid Repository : https://github.com/mantidproject/mantid
//
// Copyright &copy; 2018 ISIS Rutherford Appleton Laboratory UKRI,
//   NScD Oak Ridge National Laboratory, European Spallation Source,
//   Institut Laue - Langevin & CSNS, Institute of High Energy Physics, CAS
// SPDX - License - Identifier: GPL - 3.0 +
#include "Instrument.h"
namespace MantidQt::CustomInterfaces::ISISReflectometry {

Instrument::Instrument()
    : m_wavelengthRange(RangeInLambda(0.0, 0.0)),
      m_monitorCorrections(MonitorCorrections(0, true, RangeInLambda(0.0, 0.0), RangeInLambda(0.0, 0.0))),
      m_detectorCorrections(DetectorCorrections(false, DetectorCorrectionType::VerticalShift)) {}

Instrument::Instrument(boost::optional<RangeInLambda> wavelengthRange, MonitorCorrections monitorCorrections,
                       DetectorCorrections detectorCorrections, std::string calibrationFilePath)
    : m_wavelengthRange(std::move(wavelengthRange)), m_monitorCorrections(std::move(monitorCorrections)),
      m_detectorCorrections(detectorCorrections), m_calibrationFilePath(calibrationFilePath) {}

Instrument &Instrument::operator=(Instrument const &old_instrument) {
  m_wavelengthRange = old_instrument.wavelengthRange();
  m_monitorCorrections = old_instrument.monitorCorrections();
  m_detectorCorrections = old_instrument.detectorCorrections();
  m_calibrationFilePath = old_instrument.calibrationFilePath();
  return *this;
}

boost::optional<RangeInLambda> const &Instrument::wavelengthRange() const { return m_wavelengthRange; }

MonitorCorrections const &Instrument::monitorCorrections() const { return m_monitorCorrections; }

DetectorCorrections const &Instrument::detectorCorrections() const { return m_detectorCorrections; }

std::string const &Instrument::calibrationFilePath() const { return m_calibrationFilePath; }

size_t Instrument::monitorIndex() const { return m_monitorCorrections.monitorIndex(); }

bool Instrument::integratedMonitors() const { return m_monitorCorrections.integrate(); }

boost::optional<RangeInLambda> Instrument::monitorIntegralRange() const { return m_monitorCorrections.integralRange(); }

boost::optional<RangeInLambda> Instrument::monitorBackgroundRange() const {
  return m_monitorCorrections.backgroundRange();
}

bool Instrument::correctDetectors() const { return m_detectorCorrections.correctPositions(); }

DetectorCorrectionType Instrument::detectorCorrectionType() const { return m_detectorCorrections.correctionType(); }

bool operator!=(Instrument const &lhs, Instrument const &rhs) { return !(lhs == rhs); }

bool operator==(Instrument const &lhs, Instrument const &rhs) {
  return lhs.wavelengthRange() == rhs.wavelengthRange() && lhs.monitorCorrections() == rhs.monitorCorrections() &&
         lhs.detectorCorrections() == rhs.detectorCorrections() &&
         lhs.calibrationFilePath() == rhs.calibrationFilePath();
}
} // namespace MantidQt::CustomInterfaces::ISISReflectometry
