#include "NXcanSASTestHelper.h"
#include "MantidAPI/AlgorithmManager.h"
#include "MantidAPI/Axis.h"
#include "MantidKernel/UnitFactory.h"
#include "MantidAPI/MatrixWorkspace.h"
#include "MantidDataHandling/NXcanSASDefinitions.h"
#include "MantidGeometry/Instrument.h"
#include "MantidTestHelpers/WorkspaceCreationHelper.h"

namespace NXcanSASTestHelper
{

std::string concatenateStringVector(std::vector<std::string> stringVector)
{
    std::ostringstream os;
    for (auto &element : stringVector) {
        os << element;
        os << Mantid::DataHandling::NXcanSAS::sasSeparator;
    }

    return os.str();
}

std::string getIDFfromWorkspace(Mantid::API::MatrixWorkspace_sptr workspace)
{
    auto instrument = workspace->getInstrument();
    auto name = instrument->getFullName();
    auto date = workspace->getWorkspaceStartDate();
    return workspace->getInstrumentFilename(name, date);
}

void setXValuesOn1DWorkspaceWithPointData(
    Mantid::API::MatrixWorkspace_sptr workspace, double xmin, double xmax)
{
    auto &xValues = workspace->dataX(0);
    auto size = xValues.size();
    double binWidth = (xmax - xmin) / static_cast<double>(size - 1);
    for (size_t index = 0; index < size; ++index) {
        xValues[index] = xmin;
        xmin += binWidth;
    }
}

void add_sample_log(Mantid::API::MatrixWorkspace_sptr workspace,
                    const std::string &logName, const std::string &logValue) {
  auto logAlg = Mantid::API::AlgorithmManager::Instance().createUnmanaged(
      "AddSampleLog");
  logAlg->initialize();
  logAlg->setChild(true);
  logAlg->setProperty("Workspace", workspace);
  logAlg->setProperty("LogName", logName);
  logAlg->setProperty("LogText", logValue);
  logAlg->execute();
}

void set_logs(Mantid::API::MatrixWorkspace_sptr workspace,
              const std::string &runNumber, const std::string &userFile) {
  if (!runNumber.empty()) {
    add_sample_log(workspace, "run_number", runNumber);
  }

  if (!userFile.empty()) {
    add_sample_log(workspace, "UserFile", userFile);
  }
}

void set_instrument(Mantid::API::MatrixWorkspace_sptr workspace,
                    const std::string &instrumentName) {
  auto instAlg = Mantid::API::AlgorithmManager::Instance().createUnmanaged(
      "LoadInstrument");
  instAlg->initialize();
  instAlg->setChild(true);
  instAlg->setProperty("Workspace", workspace);
  instAlg->setProperty("InstrumentName", instrumentName);
  instAlg->setProperty("RewriteSpectraMap", "False");
  instAlg->execute();
}

Mantid::API::MatrixWorkspace_sptr
provide1DWorkspace(NXcanSASTestParameters &parameters) {
  Mantid::API::MatrixWorkspace_sptr ws;
  if (parameters.hasDx) {
    ws = WorkspaceCreationHelper::Create1DWorkspaceConstantWithXerror(
        parameters.size, parameters.value, parameters.error,
        parameters.xerror);
  } else {
    ws = WorkspaceCreationHelper::Create1DWorkspaceConstant(
        parameters.size, parameters.value, parameters.error);
  }

  ws->setTitle(parameters.workspaceTitle);
  ws->getAxis(0)->unit() =
      Mantid::Kernel::UnitFactory::Instance().create("MomentumTransfer");

  // Add sample logs
  set_logs(ws, parameters.runNumber, parameters.userFile);

  // Set instrument
  set_instrument(ws, parameters.instrumentName);

  return ws;
}

Mantid::API::MatrixWorkspace_sptr
getTransmissionWorkspace(NXcanSASTestTransmissionParameters &parameters) {
  auto ws = WorkspaceCreationHelper::Create1DWorkspaceConstant(
      parameters.size, parameters.value, parameters.error);
  ws->setTitle(parameters.name);
  ws->getAxis(0)->unit() =
      Mantid::Kernel::UnitFactory::Instance().create("Wavelength");
  return ws;
}

Mantid::API::MatrixWorkspace_sptr
provide2DWorkspace(NXcanSASTestParameters &parameters) {
  auto ws = provide1DWorkspace(parameters);

  std::string axisBinning = std::to_string(parameters.xmin) + ",1," +
                            std::to_string(parameters.xmax);
  std::string axis2Binning = std::to_string(parameters.ymin) + ",1," +
                             std::to_string(parameters.ymax);

  // Convert to Histogram data
  auto toHistAlg = Mantid::API::AlgorithmManager::Instance().createUnmanaged(
      "ConvertToHistogram");
  std::string toHistoOutputName("toHistOutput");
  toHistAlg->initialize();
  toHistAlg->setChild(true);
  toHistAlg->setProperty("InputWorkspace", ws);
  toHistAlg->setProperty("OutputWorkspace", toHistoOutputName);
  toHistAlg->execute();
  ws = toHistAlg->getProperty("OutputWorkspace");

  // Convert Spectrum Axis
  auto axisAlg = Mantid::API::AlgorithmManager::Instance().createUnmanaged(
      "ConvertSpectrumAxis");
  std::string toAxisOutputName("toAxisOutput");
  axisAlg->initialize();
  axisAlg->setChild(true);
  axisAlg->setProperty("InputWorkspace", ws);
  axisAlg->setProperty("OutputWorkspace", toAxisOutputName);
  axisAlg->setProperty("Target", "Theta");
  axisAlg->execute();
  ws = axisAlg->getProperty("OutputWorkspace");

  // Rebin 2D
  auto rebin2DAlg =
      Mantid::API::AlgorithmManager::Instance().createUnmanaged("Rebin2D");
  std::string rebinOutputName("rebinOutput");
  rebin2DAlg->initialize();
  rebin2DAlg->setChild(true);
  rebin2DAlg->setProperty("InputWorkspace", ws);
  rebin2DAlg->setProperty("OutputWorkspace", rebinOutputName);
  rebin2DAlg->setProperty("Axis1Binning", axisBinning);
  rebin2DAlg->setProperty("Axis2Binning", axis2Binning);
  rebin2DAlg->execute();
  ws = rebin2DAlg->getProperty("OutputWorkspace");

  // Convert to Point data
  auto toPointAlg = Mantid::API::AlgorithmManager::Instance().createUnmanaged(
      "ConvertToPointData");
  std::string toPointOutputName("toPointOutput");
  toPointAlg->initialize();
  toPointAlg->setChild(true);
  toPointAlg->setProperty("InputWorkspace", ws);
  toPointAlg->setProperty("OutputWorkspace", toPointOutputName);
  toPointAlg->execute();
  ws = toPointAlg->getProperty("OutputWorkspace");

  // Set the units to momentum transfer
  ws->getAxis(1)->unit() =
      Mantid::Kernel::UnitFactory::Instance().create("MomentumTransfer");

  return ws;
}

void set2DValues(Mantid::API::MatrixWorkspace_sptr ws) {
  const auto numberOfHistograms = ws->getNumberHistograms();

  for (size_t index = 0; index < numberOfHistograms; ++index) {
    auto &data = ws->dataY(index);
    data = Mantid::MantidVec(data.size(), static_cast<double>(index));
  }
}


}
