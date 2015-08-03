#ifndef GETINVESTIGATION_H_
#define GETINVESTIGATION_H_

#include <cxxtest/TestSuite.h>
#include "MantidICat/CatalogGetDataFiles.h"
#include "MantidICat/CatalogLogin.h"
#include "MantidICat/CatalogSearch.h"
#include "MantidDataObjects/WorkspaceSingleValue.h"
#include "ICatTestHelper.h"

using namespace Mantid;
using namespace Mantid::ICat;

class CatalogGetDataFilesTest: public CxxTest::TestSuite
{
public:
  /// Skip all unit tests if ICat server is down
  bool skipTests()
  {
    return ICatTestHelper::skipTests();
  }

	void testInit()
	{
		Mantid::Kernel::ConfigService::Instance().setString("default.facility", "ISIS");
		TS_ASSERT_THROWS_NOTHING( invstObj.initialize());
		TS_ASSERT( invstObj.isInitialized() );
	}

	void testgetDataFilesExecutes()
	{	
		if ( !loginobj.isInitialized() ) loginobj.initialize();

		loginobj.setPropertyValue("Username", "mantidtest@fitsp10.isis.cclrc.ac.uk");
		loginobj.setPropertyValue("Password", "MantidTestUser4");
		
		TS_ASSERT_THROWS_NOTHING(loginobj.execute());
		TS_ASSERT( loginobj.isExecuted() );

		if (!invstObj.isInitialized() ) invstObj.initialize();
		invstObj.setPropertyValue("InvestigationId","12576918");
		invstObj.setPropertyValue("OutputWorkspace","investigation");//selected invesigation data files
		
		TS_ASSERT_THROWS_NOTHING(invstObj.execute());
		TS_ASSERT( invstObj.isExecuted() );
	}
private:
	CatalogLogin loginobj;
	CatalogGetDataFiles invstObj;
};
#endif
