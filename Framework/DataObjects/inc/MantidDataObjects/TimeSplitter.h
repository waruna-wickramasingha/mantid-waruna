// Mantid Repository : https://github.com/mantidproject/mantid
//
// Copyright &copy; 2012 ISIS Rutherford Appleton Laboratory UKRI,
//   NScD Oak Ridge National Laboratory, European Spallation Source,
//   Institut Laue - Langevin & CSNS, Institute of High Energy Physics, CAS
// SPDX - License - Identifier: GPL - 3.0 +
#pragma once

#include "MantidAPI/MatrixWorkspace.h"
#include "MantidDataObjects/DllConfig.h"
#include "MantidDataObjects/SplittersWorkspace.h"
#include "MantidDataObjects/TableWorkspace.h"
#include "MantidKernel/DateAndTime.h"

#include <set>

namespace Mantid {

using Types::Core::DateAndTime;

namespace Kernel {
class TimeROI; // Forward declaration
}

namespace DataObjects {

class EventList; // Forward declaration

class MANTID_DATAOBJECTS_DLL TimeSplitter {

public:
  // some temprorary timing helpers
  static double getTime1();
  static double getTime2();
  static double getTime4();
  static double getTime5();
  // static double getTime10();

  static constexpr int NO_TARGET{-1}; // no target (a.k.a. destination) workspace for filtered out events
  TimeSplitter() = default;
  TimeSplitter(const DateAndTime &start, const DateAndTime &stop, const int value = DEFAULT_TARGET);
  TimeSplitter(const Mantid::API::MatrixWorkspace_sptr &ws, const DateAndTime &offset = DateAndTime::GPS_EPOCH);
  TimeSplitter(const TableWorkspace_sptr &tws, const DateAndTime &offset = DateAndTime::GPS_EPOCH);
  TimeSplitter(const SplittersWorkspace_sptr &sws);
  const std::map<DateAndTime, int> &getSplittersMap() const;
  std::string getWorkspaceIndexName(const int workspaceIndex, const int numericalShift = 0);
  /// Find the destination index for an event with a given time
  int valueAtTime(const DateAndTime &time) const;
  void addROI(const DateAndTime &start, const DateAndTime &stop, const int value);
  /// Check if the TimeSplitter is empty
  bool empty() const;
  std::set<int> outputWorkspaceIndices() const;
  Kernel::TimeROI getTimeROI(const int workspaceIndex);
  /// Cast to to vector of SplittingInterval objects
  Kernel::SplittingIntervalVec toSplitters(const bool includeNoTarget = true) const;
  /// this is to aid in testing and not intended for use elsewhere
  std::size_t numRawValues() const;
  /// Split a list of events according to Pulse time or Pulse + TOF time
  void splitEventList(const EventList &events, std::map<int, EventList *> &partials, const bool pulseTof = false,
                      const bool tofCorrect = false, const double factor = 1.0, const double shift = 0.0) const;
  /// Print the (destination index | DateAndTime boundary) pairs of this splitter.
  std::string debugPrint() const;
  void rebuildCachedPartialTimeROIs();

private:
  static constexpr int DEFAULT_TARGET{0};
  void clearAndReplace(const DateAndTime &start, const DateAndTime &stop, const int value);
  /// Distribute a list of events by comparing a vector of times against the splitter boundaries.
  template <typename EventType>
  void splitEventVec(const std::vector<EventType> &events, std::map<int, EventList *> &partials, const bool pulseTof,
                     const bool tofCorrect, const double factor, const double shift) const;
  template <typename EventType>
  void splitEventVec(const std::function<const DateAndTime(const EventType &)> &timeCalc,
                     const std::vector<EventType> &events, std::map<int, EventList *> &partials) const;

  void resetCachedPartialTimeROIs();

  std::map<DateAndTime, int> m_roi_map;
  // These 2 maps are complementary to each other
  std::map<std::string, int> m_name_index_map;
  std::map<int, std::string> m_index_name_map;

  std::map<int, Kernel::TimeROI> m_cachedPartialTimeROIs;
  bool validCachedPartialTimeROIs{false};
};
} // namespace DataObjects
} // namespace Mantid
