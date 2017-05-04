#include "MantidMDAlgorithms/IntegrateEllipsoidsTwoStep.h"

#include "MantidAPI/InstrumentValidator.h"
#include "MantidAPI/Run.h"
#include "MantidAPI/Sample.h"
#include "MantidDataObjects/PeaksWorkspace.h"
#include "MantidDataObjects/PeakShapeEllipsoid.h"
#include "MantidDataObjects/Workspace2D.h"
#include "MantidDataObjects/EventWorkspace.h"
#include "MantidGeometry/Crystal/IndexingUtils.h"
#include "MantidGeometry/Crystal/OrientedLattice.h"
#include "MantidKernel/BoundedValidator.h"
#include "MantidKernel/CompositeValidator.h"
#include "MantidKernel/make_unique.h"
#include "MantidKernel/NearestNeighbours.h"
#include "MantidMDAlgorithms/Integrate3DEvents.h"
#include "MantidMDAlgorithms/MDTransfFactory.h"
#include "MantidMDAlgorithms/MDTransfQ3D.h"
#include "MantidMDAlgorithms/UnitsConversionHelper.h"

#include <string>
#include <tuple>
#include <boost/math/special_functions/round.hpp>

using namespace Mantid::API;
using namespace Mantid::DataObjects;
using namespace Mantid::Kernel;

namespace Mantid {
namespace MDAlgorithms {

// Register the algorithm into the AlgorithmFactory
DECLARE_ALGORITHM(IntegrateEllipsoidsTwoStep)

//---------------------------------------------------------------------
/// Algorithm's name for identification. @see Algorithm::name
const std::string IntegrateEllipsoidsTwoStep::name() const {
  return "IntegrateEllipsoidsTwoStep";
}

/// Algorithm's version for identification. @see Algorithm::version
int IntegrateEllipsoidsTwoStep::version() const { return 1; }

/// Algorithm's category for identification. @see Algorithm::category
const std::string IntegrateEllipsoidsTwoStep::category() const {
  return "Crystal\\Integration";
}

void IntegrateEllipsoidsTwoStep::init() {
  auto ws_valid = boost::make_shared<CompositeValidator>();
  ws_valid->add<InstrumentValidator>();

  auto mustBePositive = boost::make_shared<BoundedValidator<double>>();
  mustBePositive->setLower(0.0);

  declareProperty(make_unique<WorkspaceProperty<MatrixWorkspace>>(
                      "InputWorkspace", "", Direction::Input, ws_valid),
                  "An input MatrixWorkspace with time-of-flight units along "
                  "X-axis and defined instrument with defined sample");

  declareProperty(make_unique<WorkspaceProperty<PeaksWorkspace>>(
                      "PeaksWorkspace", "", Direction::InOut),
                  "Workspace with peaks to be integrated");

  declareProperty("RegionRadius", .35, mustBePositive,
                  "Only events at most this distance from a peak will be "
                  "considered when integrating");

  declareProperty(
      "SpecifySize", false,
      "If true, use the following for the major axis sizes, else use 3-sigma");

  declareProperty("PeakSize", .18, mustBePositive,
                  "Half-length of major axis for peak ellipsoid");

  declareProperty("BackgroundInnerSize", .18, mustBePositive,
                  "Half-length of major axis for inner ellipsoidal surface of "
                  "background region");

  declareProperty("BackgroundOuterSize", .23, mustBePositive,
                  "Half-length of major axis for outer ellipsoidal surface of "
                  "background region");

  declareProperty("WeakPeakThreshold", 1.0, mustBePositive,
                  "Intensity threshold use to classify a peak as weak.");

  declareProperty(
      make_unique<WorkspaceProperty<PeaksWorkspace>>("OutputWorkspace", "",
                                                     Direction::Output),
      "The output PeaksWorkspace will be a copy of the input PeaksWorkspace "
      "with the peaks' integrated intensities.");
}

void IntegrateEllipsoidsTwoStep::exec() {
  PeaksWorkspace_sptr input_peak_ws = getProperty("PeaksWorkspace");
  MatrixWorkspace_sptr input_ws = getProperty("InputWorkspace");
  EventWorkspace_sptr eventWS =
      boost::dynamic_pointer_cast<EventWorkspace>(input_ws);

  Workspace2D_sptr histoWS = boost::dynamic_pointer_cast<Workspace2D>(input_ws);
  if (!eventWS && !histoWS) {
    throw std::runtime_error("IntegrateEllipsoids needs either a "
                             "EventWorkspace or Workspace2D as input.");
  }

  const double weakPeakThreshold = getProperty("WeakPeakThreshold");

  // validation of inputs
  if (!input_peak_ws) {
    throw std::runtime_error("Could not read the Peaks Workspace");
  }

  if (!input_ws) {
    throw std::runtime_error("Could not read the Input Workspace");
  }

  PeaksWorkspace_sptr peak_ws = getProperty("OutputWorkspace");
  if (peak_ws != input_peak_ws) {
    peak_ws = input_peak_ws->clone();
  }

  Progress prog(this, 0.5, 1.0, input_ws->getNumberHistograms());

  const auto& UB = input_peak_ws->sample().getOrientedLattice().getUB();
  auto UBinv = UB;
  UBinv.Invert();
  UBinv *= (1.0 / (2.0 * M_PI));

  std::vector<Peak> &peaks = peak_ws->getPeaks();
  size_t n_peaks = peak_ws->getNumberPeaks();
  std::vector<std::pair<double, V3D>> qList;
  for (size_t i = 0; i < n_peaks; i++)
  {
    qList.emplace_back(1., V3D(peaks[i].getQLabFrame()));
  }

  IntegrationParameters params;
  params.peakRadius = getProperty("PeakSize");
  params.backgroundInnerRadius = getProperty("BackgroundInnerSize");
  params.backgroundOuterRadius = getProperty("BackgroundOuterSize");
  params.regionRadius = getProperty("RegionRadius");
  params.specifySize = getProperty("SpecifySize");

  Integrate3DEvents integrator(qList, UBinv, params.regionRadius);

  if (eventWS) {
    // process as EventWorkspace
    qListFromEventWS(integrator, prog, eventWS, UBinv, false);
  } else {
    // process as Workspace2D
    qListFromHistoWS(integrator, prog, histoWS, UBinv, false);
  }

  std::vector<std::pair<int, V3D>> weakPeaks, strongPeaks;

  // Compute signal to noise ratio for all peaks
  int index = 0;
  for (const auto& item : qList) {
    const auto center = item.second;

    auto sig2noise = integrator.estimateSignalToNoiseRatio(params, center);

    auto& peak = peak_ws->getPeak(index);
    peak.setIntensity(0);
    peak.setSigmaIntensity(0);

    const auto result = std::make_pair(index, center);
    if (sig2noise < weakPeakThreshold) {
      g_log.information() << "Peak " << peak.getHKL() <<  " with Q = " << center << " is a weak peak with signal to noise " << sig2noise << "\n";
      weakPeaks.push_back(result);
    } else {
      g_log.information() << "Peak " << peak.getHKL() <<  " with Q = " << center << " is a strong peak with signal to noise " << sig2noise << "\n";
      strongPeaks.push_back(result);
    }
    ++index;
  }

  std::vector<std::pair<boost::shared_ptr<const Geometry::PeakShape>, std::pair<double, double>>> shapeLibrary;

  // Integrate strong peaks
  for (const auto& item : strongPeaks) {
    const auto index = item.first;
    const auto q = item.second;
    double inti, sigi;

    const auto result = integrator.integrateStrongPeak(params, q, inti, sigi);
    shapeLibrary.push_back(result);

    auto& peak = peak_ws->getPeak(index);
    peak.setIntensity(inti);
    peak.setSigmaIntensity(sigi);
    peak.setPeakShape(std::get<0>(result));
  }

  std::vector<Eigen::Vector3d> points;
  std::transform(strongPeaks.begin(), strongPeaks.end(), std::back_inserter(points),
                 [&](const std::pair<int, V3D>& item) {
    const auto q = item.second;
    return Eigen::Vector3d(q[0], q[1], q[2]);
  });

  if (points.empty())
    throw std::runtime_error("Cannot integrate peaks when all peaks are below "
                             "the signal to noise ratio.");

  NearestNeighbours<3> kdTree(points);

  // Integrate weak peaks
  for (const auto& item : weakPeaks) {
    double inti, sigi;
    const auto index = item.first;
    const auto q = item.second;

    const auto result = kdTree.findNearest(Eigen::Vector3d(q[0], q[1], q[2]));
    const auto strongIndex = static_cast<int>(std::get<1>(result[0]));

    auto& peak = peak_ws->getPeak(index);
    auto& strongPeak = peak_ws->getPeak(strongIndex);

    g_log.information() << "Integrating weak peak " << peak.getHKL() << " using strong peak " << strongPeak.getHKL() << "\n";

    const auto libShape = shapeLibrary[static_cast<int>(strongIndex)];
    const auto shape = boost::dynamic_pointer_cast<const PeakShapeEllipsoid>(libShape.first);
    const auto frac = libShape.second.first;

    g_log.information() << "Weak peak will be adjusted by " << frac << "\n";
    const auto weakShape = integrator.integrateWeakPeak(params, shape, libShape.second, q, inti, sigi);

    peak.setIntensity(inti);
    peak.setSigmaIntensity(sigi);
    peak.setPeakShape(weakShape);
  }


  // This flag is used by the PeaksWorkspace to evaluate whether it has been
  // integrated.
  peak_ws->mutableRun().addProperty("PeaksIntegrated", 1, true);
  setProperty("OutputWorkspace", peak_ws);
}


void IntegrateEllipsoidsTwoStep::qListFromEventWS(Integrate3DEvents &integrator,
                                           Progress &prog,
                                           EventWorkspace_sptr &wksp,
                                           DblMatrix const &UBinv,
                                           bool hkl_integ) {
  // loop through the eventlists

  const std::string ELASTIC("Elastic");
  /// Only convert to Q-vector.
  const std::string Q3D("Q3D");
  const std::size_t DIMS(3);

  MDWSDescription m_targWSDescr;
  m_targWSDescr.setMinMax(std::vector<double>(3, -2000.),
                          std::vector<double>(3, 2000.));
  m_targWSDescr.buildFromMatrixWS(wksp, Q3D, ELASTIC);
  m_targWSDescr.setLorentsCorr(false);

  // generate the detectors table
  Mantid::API::Algorithm_sptr childAlg = createChildAlgorithm(
      "PreprocessDetectorsToMD", 0.,
      .5); // HACK. soft dependency on non-dependent package.
  childAlg->setProperty("InputWorkspace", wksp);
  childAlg->executeAsChildAlg();

  DataObjects::TableWorkspace_sptr table =
      childAlg->getProperty("OutputWorkspace");
  if (!table)
    throw(std::runtime_error(
        "Can not retrieve results of \"PreprocessDetectorsToMD\""));

  m_targWSDescr.m_PreprDetTable = table;


  int numSpectra = static_cast<int>(wksp->getNumberHistograms());
  PARALLEL_FOR_IF(Kernel::threadSafe(*wksp))
  for (int i = 0; i < numSpectra; ++i) {
    PARALLEL_START_INTERUPT_REGION

    // units conversion helper
    UnitsConversionHelper unitConverter;
    unitConverter.initialize(m_targWSDescr, "Momentum");

    // initialize the MD coordinates conversion class
    MDTransfQ3D qConverter;
    qConverter.initialize(m_targWSDescr);

    std::vector<double> buffer(DIMS);
    // get a reference to the event list
    EventList &events = wksp->getSpectrum(i);

    events.switchTo(WEIGHTED_NOTIME);
    events.compressEvents(1e-5, &events);

    // check to see if the event list is empty
    if (events.empty()) {
      prog.report();
      continue; // nothing to do
    }

    // update which pixel is being converted
    std::vector<Mantid::coord_t> locCoord(DIMS, 0.);
    unitConverter.updateConversion(i);
    qConverter.calcYDepCoordinates(locCoord, i);

    // loop over the events
    double signal(1.);  // ignorable garbage
    double errorSq(1.); // ignorable garbage
    const std::vector<WeightedEventNoTime> &raw_events =
        events.getWeightedEventsNoTime();
    std::vector<std::pair<double, V3D>> qList;
    for (const auto &raw_event : raw_events) {
      double val = unitConverter.convertUnits(raw_event.tof());
      qConverter.calcMatrixCoord(val, locCoord, signal, errorSq);
      for (size_t dim = 0; dim < DIMS; ++dim) {
        buffer[dim] = locCoord[dim];
      }
      V3D qVec(buffer[0], buffer[1], buffer[2]);
      if (hkl_integ)
        qVec = UBinv * qVec;
      qList.emplace_back(raw_event.m_weight, qVec);
    } // end of loop over events in list
    PARALLEL_CRITICAL(addEvents) { integrator.addEvents(qList, hkl_integ); }

    prog.report();
    PARALLEL_END_INTERUPT_REGION
  } // end of loop over spectra
  PARALLEL_CHECK_INTERUPT_REGION
}

/**
 * @brief qListFromHistoWS creates qlist from input workspaces of type
 * Workspace2D
 * @param integrator : itegrator object on which qlists are accumulated
 * @param prog : progress object
 * @param wksp : input Workspace2D
 * @param UBinv : inverse of UB matrix
 * @param hkl_integ ; boolean for integrating in HKL space
 */
void IntegrateEllipsoidsTwoStep::qListFromHistoWS(Integrate3DEvents &integrator,
                                           Progress &prog,
                                           Workspace2D_sptr &wksp,
                                           DblMatrix const &UBinv,
                                           bool hkl_integ) {

  // loop through the eventlists
  const std::string ELASTIC("Elastic");
  /// Only convert to Q-vector.
  const std::string Q3D("Q3D");
  const std::size_t DIMS(3);

  MDWSDescription m_targWSDescr;
  m_targWSDescr.setMinMax(std::vector<double>(3, -2000.),
                          std::vector<double>(3, 2000.));
  m_targWSDescr.buildFromMatrixWS(wksp, Q3D, ELASTIC);
  m_targWSDescr.setLorentsCorr(false);

  // generate the detectors table
  Mantid::API::Algorithm_sptr childAlg = createChildAlgorithm(
      "PreprocessDetectorsToMD", 0.,
      .5); // HACK. soft dependency on non-dependent package.
  childAlg->setProperty("InputWorkspace", wksp);
  childAlg->executeAsChildAlg();

  DataObjects::TableWorkspace_sptr table =
      childAlg->getProperty("OutputWorkspace");
  if (!table)
    throw(std::runtime_error(
        "Can not retrieve results of \"PreprocessDetectorsToMD\""));
  else
    m_targWSDescr.m_PreprDetTable = table;

  int numSpectra = static_cast<int>(wksp->getNumberHistograms());
  PARALLEL_FOR_IF(Kernel::threadSafe(*wksp))
  for (int i = 0; i < numSpectra; ++i) {
    PARALLEL_START_INTERUPT_REGION

    // units conversion helper
    UnitsConversionHelper unitConverter;
    unitConverter.initialize(m_targWSDescr, "Momentum");

    // initialize the MD coordinates conversion class
    MDTransfQ3D qConverter;
    qConverter.initialize(m_targWSDescr);

    std::vector<double> buffer(DIMS);
    // get tof and counts
    const auto &xVals = wksp->points(i);
    const auto &yVals = wksp->counts(i);

    // update which pixel is being converted
    std::vector<Mantid::coord_t> locCoord(DIMS, 0.);
    unitConverter.updateConversion(i);
    qConverter.calcYDepCoordinates(locCoord, i);

    // loop over the events
    double signal(1.);  // ignorable garbage
    double errorSq(1.); // ignorable garbage

    std::vector<std::pair<double, V3D>> qList;

    for (size_t j = 0; j < yVals.size(); ++j) {
      const double &yVal = yVals[j];
      if (yVal > 0) // TODO, is this condition right?
      {
        double val = unitConverter.convertUnits(xVals[j]);
        qConverter.calcMatrixCoord(val, locCoord, signal, errorSq);
        V3D qVec(locCoord[0], locCoord[1], locCoord[2]);
        if (hkl_integ)
          qVec = UBinv * qVec;

        if(isnan(qVec[0]) || isnan(qVec[1]) || isnan(qVec[2]))
          continue;
        // Account for counts in histograms by increasing the qList with the
        // same q-point
        qList.emplace_back(yVal, qVec);
      }
    }
    PARALLEL_CRITICAL(addHisto) { integrator.addEvents(qList, hkl_integ); }
    prog.report();
    PARALLEL_END_INTERUPT_REGION
  } // end of loop over spectra
  PARALLEL_CHECK_INTERUPT_REGION
}

}
}
