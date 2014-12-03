#ifndef MANTID_SINQ_POLDIFITPEAKS1D2TEST_H_
#define MANTID_SINQ_POLDIFITPEAKS1D2TEST_H_

#include <cxxtest/TestSuite.h>

#include "MantidSINQ/PoldiFitPeaks1D2.h"

#include "MantidAPI/IFunction.h"
#include "MantidAPI/CompositeFunction.h"
#include "MantidAPI/IPeakFunction.h"

#include "MantidCurveFitting/Gaussian.h"
#include "MantidCurveFitting/FlatBackground.h"

#include "MantidSINQ/PoldiUtilities/PoldiPeak.h"

using Mantid::Poldi::PoldiFitPeaks1D2;
using namespace Mantid::Poldi;
using namespace Mantid::API;
using namespace Mantid::CurveFitting;
using namespace Mantid::Kernel;

class PoldiFitPeaks1D2;

class TestablePoldiFitPeaks1D2 : public Mantid::Poldi::PoldiFitPeaks1D2
{
    friend class PoldiFitPeaks1D2Test;
public:
    TestablePoldiFitPeaks1D2() :
        PoldiFitPeaks1D2()
    {
    }
};

class PoldiFitPeaks1D2Test : public CxxTest::TestSuite
{
public:
    // This pair of boilerplate methods prevent the suite being created statically
    // This means the constructor isn't called when running other tests
    static PoldiFitPeaks1D2Test *createSuite() { return new PoldiFitPeaks1D2Test(); }
    static void destroySuite( PoldiFitPeaks1D2Test *suite ) { delete suite; }

    PoldiFitPeaks1D2Test()
    {
        m_testPeak = PoldiPeak::create(MillerIndices(1, 1, 1), UncertainValue(1.108329), UncertainValue(2948.231), UncertainValue(0.002));
        m_profileTestFunction = std::string("Gaussian");
        m_backgroundTestFunction = IFunction_sptr(new FlatBackground);
        m_backgroundTestFunction->initialize();
    }

    void testSetPeakFunction()
    {
        TestablePoldiFitPeaks1D2 poldiFitPeaks;
        poldiFitPeaks.setPeakFunction(m_profileTestFunction);

        TS_ASSERT_EQUALS(poldiFitPeaks.m_profileTemplate, m_profileTestFunction);
    }

    void testGetPeakProfile()
    {
        TestablePoldiFitPeaks1D2 poldiFitPeaks;
        poldiFitPeaks.initialize();
        poldiFitPeaks.setPeakFunction(m_profileTestFunction);

        IFunction_sptr peakFunction = poldiFitPeaks.getPeakProfile(m_testPeak);

        // make sure that the profile is correct
        IPeakFunction_sptr profile = boost::dynamic_pointer_cast<IPeakFunction>(peakFunction);
        TS_ASSERT(profile);

        TS_ASSERT_EQUALS(profile->centre(), m_testPeak->q());
        TS_ASSERT_EQUALS(profile->height(), m_testPeak->intensity());
        TS_ASSERT_EQUALS(profile->fwhm(), m_testPeak->fwhm(PoldiPeak::AbsoluteQ));
    }

    void testSetValuesFromProfileFunction()
    {
        TestablePoldiFitPeaks1D2 poldiFitPeaks;
        poldiFitPeaks.initialize();
        poldiFitPeaks.setPeakFunction(m_profileTestFunction);

        IFunction_sptr totalProfile = poldiFitPeaks.getPeakProfile(m_testPeak);

        // now we have a profile with known parameters. assign them to a new PoldiPeak
        PoldiPeak_sptr newPeak = PoldiPeak::create(1.0);
        poldiFitPeaks.setValuesFromProfileFunction(newPeak, totalProfile);

        TS_ASSERT_EQUALS(newPeak->q(), m_testPeak->q());
        TS_ASSERT_EQUALS(newPeak->intensity(), m_testPeak->intensity());
        TS_ASSERT_EQUALS(newPeak->fwhm(PoldiPeak::AbsoluteQ), m_testPeak->fwhm(PoldiPeak::AbsoluteQ));
    }

    void testProperties()
    {
        Mantid::Poldi::PoldiFitPeaks1D2 fitPeaks1D;
        fitPeaks1D.initialize();

        TS_ASSERT_EQUALS(fitPeaks1D.propertyCount(), 7);

        std::vector<Property *> properties = fitPeaks1D.getProperties();
        std::set<std::string> names;

        for(size_t i = 0; i < properties.size(); ++i) {
            names.insert(properties[i]->name());
        }

        TS_ASSERT_EQUALS(names.count("InputWorkspace"), 1);
        TS_ASSERT_EQUALS(names.count("FwhmMultiples"), 1);
        TS_ASSERT_EQUALS(names.count("PeakFunction"), 1);
        TS_ASSERT_EQUALS(names.count("PoldiPeakTable"), 1);
        TS_ASSERT_EQUALS(names.count("OutputWorkspace"), 1);
        TS_ASSERT_EQUALS(names.count("ResultTableWorkspace"), 1);
        TS_ASSERT_EQUALS(names.count("FitPlotsWorkspace"), 1);
    }

private:
    PoldiPeak_sptr m_testPeak;
    std::string m_profileTestFunction;
    IFunction_sptr m_backgroundTestFunction;
};


#endif /* MANTID_SINQ_POLDIFITPEAKS1D2TEST_H_ */
