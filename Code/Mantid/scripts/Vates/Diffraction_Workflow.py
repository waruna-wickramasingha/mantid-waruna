# Basic parameters  for  Triphylite Crystal
filename = "TOPAZ_3131_event.nxs"
#Name of the workspaces to create
ws = "TOPAZ_3131"
LoadEventNexus(Filename=filename,OutputWorkspace=ws,FilterByTofMin='3000',FilterByTofMax='16000')
# Load optimized DetCal file
LoadIsawDetCal(InputWorkspace=ws,Filename="/SNS/TOPAZ/shared/Spectra/TOPAZ_8Sept11.DetCal")
# Spherical Absorption and Lorentz Corrections
AnvredCorrection(InputWorkspace=ws,OutputWorkspace=ws,LinearScatteringCoef="0.451",LinearAbsorptionCoef="0.993",Radius="0.14")
# Convert to Q space
ConvertToDiffractionMDWorkspace(InputWorkspace=ws,OutputWorkspace=ws+'_MD2',LorentzCorrection='0',
        SplitInto='2',SplitThreshold='150')
# Find peaks
FindPeaksMD(InputWorkspace=ws+'_MD2',MaxPeaks='100',OutputWorkspace=ws+'_peaksLattice')
# Find the UB matrix using the peaks and known lattice parameters
FindUBUsingLatticeParameters(PeaksWorkspace=ws+'_peaksLattice',a='10.3522',b='6.0768',c='4.7276',
                alpha='90',beta='90',gamma='90', NumInitial='20', Tolerance='0.12')
# And index to HKL            
IndexPeaks(PeaksWorkspace=ws+'_peaksLattice', Tolerance='0.12')
# 3d integration to centroid peaks
CentroidPeaksMD(InputWorkspace=ws+'_MD2',CoordinatesToUse='Q (sample frame)',PeakRadius='0.01',PeaksWorkspace=ws+'_peaksLattice',OutputWorkspace=ws+'_peaksLattice')
# Integrate peaks in Q space using spheres
IntegratePeaksMD(InputWorkspace=ws+'_MD2',PeakRadius='0.02',BackgroundRadius='0.03',BackgroundStartRadius='0.025',PeaksWorkspace=ws+'_peaksLattice',OutputWorkspace=ws+'_peaksLattice')
# Save for SHELX
SaveHKL(InputWorkspace=ws+'_peaksLattice', Filename=ws+'.hkl',LinearScatteringCoef="0.451",LinearAbsorptionCoef="0.993",Radius="0.14")

# Find peaks again for FFT
FindPeaksMD(InputWorkspace=ws+'_MD2',MaxPeaks='100',OutputWorkspace=ws+'_peaksFFT')
# Find the UB matrix using FFT
FindUBUsingFFT(PeaksWorkspace=ws+'_peaksFFT',MinD=3.,MaxD=14.)
# And index to HKL            
IndexPeaks(PeaksWorkspace=ws+'_peaksFFT', Tolerance='0.12')
# 3d integration to centroid peaks
CentroidPeaksMD(InputWorkspace=ws+'_MD2',CoordinatesToUse='Q (sample frame)',PeakRadius='0.01',PeaksWorkspace=ws+'_peaksFFT',OutputWorkspace=ws+'_peaksFFT')
# Integrate peaks in Q space using spheres
IntegratePeaksMD(InputWorkspace=ws+'_MD2',PeakRadius='0.02',BackgroundRadius='0.03',BackgroundStartRadius='0.025',PeaksWorkspace=ws+'_peaksFFT',OutputWorkspace=ws+'_peaksFFT')
# Save for SHELX
SaveHKL(InputWorkspace=ws+'_peaksFFT', Filename=ws+'FFT.hkl',LinearScatteringCoef="0.451",LinearAbsorptionCoef="0.993",Radius="0.14")


# Copy the UB matrix back to the original workspace
CopySample(InputWorkspace=ws+'_peaksLattice',OutputWorkspace=ws,
		CopyName='0',CopyMaterial='0',CopyEnvironment='0',CopyShape='0',  CopyLattice=1)
# Convert to reciprocal space, in the sample frame
ConvertToDiffractionMDWorkspace(InputWorkspace=ws,OutputWorkspace=ws+'_HKL',
		OutputDimensions='HKL',LorentzCorrection='1', SplitInto='2',SplitThreshold='150')
# Bin to a regular grid
BinMD(InputWorkspace='TOPAZ_3131_HKL',AlignedDimX='H, -20, 0, 200',AlignedDimY='K, -10, 10, 200',AlignedDimZ='L, -20, 0,  200',OutputWorkspace='TOPAZ_3131_binned')
# Show in slice Viewer		
sv = plotSlice('TOPAZ_3131_binned', xydim=('H','L'), slicepoint=[0, -2, 0], colorscalelog=True)
# Save that for later viewing in paraview
#SaveMD(InputWorkspace=ws+'_HKL', Filename='TOPAZ_3131_MD_HKL.nxs')


