from __future__ import (absolute_import, division, print_function)

from six import iteritems
import math

import mantid.simpleapi as mantid


class FFTModel(object):

    def __init__(self):
        self.name="FFT"

    def setRun(self,run):
        self.runName=run

    def preAlg(self,preInputs):
        preAlg=mantid.AlgorithmManager.create("PaddingAndApodization")
        preAlg.initialize()
        preAlg.setChild(True)
        for name,value in iteritems(preInputs):
            preAlg.setProperty(name,value)
        preAlg.execute()
        mantid.AnalysisDataService.addOrReplace(preInputs["OutputWorkspace"],preAlg.getProperty("OutputWorkspace").value)

    def FFTAlg(self,FFTInputs):
        alg=mantid.AlgorithmManager.create("FFT")
        alg.initialize()
        alg.setChild(True)
        for name,value in iteritems(FFTInputs):
            alg.setProperty(name,value)
        alg.execute()
        mantid.AnalysisDataService.addOrReplace(FFTInputs["OutputWorkspace"],alg.getProperty("OutputWorkspace").value)

        ws=alg.getPropertyValue("OutputWorkspace")
        group = mantid.AnalysisDataService.retrieve(self.runName)
        group.add(ws)

    def makePhaseQuadTable(self,axis,instrument):
        wsAlg=mantid.AlgorithmManager.create("CreateSimulationWorkspace")
        wsAlg.initialize()
        wsAlg.setChild(True)
        wsAlg.setProperty("Instrument",instrument)
        wsAlg.setProperty("BinParams","0,1,32")
        wsAlg.setProperty("OutputWorkspace","__tmp__")
        wsAlg.execute()
        output=wsAlg.getProperty("OutputWorkspace").value

        tableAlg=mantid.AlgorithmManager.create("CreateEmptyTableWorkspace")
        tableAlg.initialize()
        tableAlg.setChild(False)
        tableAlg.setProperty("OutputWorkspace","PhaseTable")
        tableAlg.execute()

        phaseTable=mantid.AnalysisDataService.retrieve("PhaseTable")
        phaseTable.addColumn("int","DetectorID")
        phaseTable.addColumn("double","Phase")
        phaseTable.addColumn("double","Asym")

        for j in range(output.getNumberHistograms()):
            det = output.getDetector(j).getPos()-output.getInstrument().getSample().getPos()
            r=math.sqrt(det.X()**2+det.Y()**2+det.Z()**2)
            if(axis=="x"):
                phi=math.atan2(det.Z(),det.Y())
                asym=math.sqrt(det.Z()**2+det.Y()**2)/r
            elif(axis=="y"):
                phi=math.atan2(det.X(),det.Z())
                asym=math.sqrt(det.X()**2+det.Z()**2)/r
            else: # z
                phi=math.atan2(det.Y(),det.X())
                asym=math.sqrt(det.Y()**2+det.X()**2)/r
            phaseTable.addRow([j,asym,phi])

    def PhaseQuad(self):
        #need to load the data as a 'raw' file
        loadAlg=mantid.AlgorithmManager.create("Load")
        loadAlg.initialize()
        loadAlg.setChild(False)
        loadAlg.setProperty("Filename",self.runName+".nxs")
        loadAlg.setProperty("OutputWorkspace","__data__")
        loadAlg.execute()

        phaseQuad=mantid.AlgorithmManager.create("PhaseQuad")
        phaseQuad.initialize()
        phaseQuad.setChild(False)
        print (self.runName)
        phaseQuad.setProperty("InputWorkspace","__data__")
        phaseQuad.setProperty("PhaseTable","PhaseTable")
        phaseQuad.setProperty("OutputWorkspace","__phaseQuad__")
        phaseQuad.execute()

    def getName(self):
        return self.name
