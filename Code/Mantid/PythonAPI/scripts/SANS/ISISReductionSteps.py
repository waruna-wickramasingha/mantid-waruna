"""
    Implementation of reduction steps for ISIS SANS instruments
    
    Most of this code is a copy-paste from SANSReduction.py, organized to be used with
    ReductionStep objects. The guts needs refactoring.
"""
from Reducer import ReductionStep
import ISISReducer
import SANSReductionSteps
from mantidsimple import *
import SANSUtility
import SANSInsts
import os
import math
import copy

#TODO: remove when center finding is working 
DEL__FINDING_CENTRE_ = False

def _issueWarning(msg):
    """
        Issues a Mantid message
        @param msg: message to be issued
    """
    mantid.sendLogMessage('::SANS::Warning: ' + msg)


class LoadRun(ReductionStep):
    """
        Load a data file, move its detector to the right position according
        to the beam center and normalize the data.
    """
    def __init__(self, data_file=None, spec_min=None, spec_max=None, period=1):
        #TODO: data_file = None only makes sense when AppendDataFile is used... (AssignSample?)
        super(LoadRun, self).__init__()
        self._data_file = data_file
        self._spec_min = spec_min
        self._spec_max = spec_max
        self._period = period
        
    def execute(self, reducer, workspace):
        # If we don't have a data file, look up the workspace handle
        if self._data_file is None:
            if workspace in reducer._data_files:
                #self._data_file = reducer._data_files[workspace]
                self._data_file = reducer._full_file_path(reducer._data_files[workspace])
            else:
                raise RuntimeError, "ISISReductionSteps.LoadRun doesn't recognize workspace handle %s" % workspace
        
        if os.path.splitext(self._data_file)[1].lower().startswith('.n'):
            alg = LoadNexus(self._data_file, workspace, SpectrumMin=self._spec_min, SpectrumMax=self._spec_max)
        else:
            alg = LoadRaw(self._data_file, workspace, SpectrumMin=self._spec_min, SpectrumMax=self._spec_max)
            LoadSampleDetailsFromRaw(workspace, self._data_file)
    
        pWorksp = mantid[workspace]
    
        if pWorksp.isGroup() :
            #get the number of periods in a group using the fact that each period has a different name
            nNames = len(pWorksp.getNames())
            numPeriods = nNames - 1
            workspace = self._leaveSinglePeriod(pWorksp, self._period)
            pWorksp = mantid[workspace]
        else :
            #if the work space isn't a group there is only one period
            numPeriods = 1
            
        if (self._period > numPeriods) or (self._period < 1):
            raise ValueError('_loadRawData: Period number ' + str(self._period) + ' doesn\'t exist in workspace ' + pWorksp.getName())
        
        # Return the file path actually used to load the data
        fullpath = alg.getPropertyValue("Filename")

        return [ os.path.dirname(fullpath), workspace, numPeriods]        

    # Helper function
    def _assignHelper(self, reducer, run_string, is_trans, reload = True, period = -1):
        if run_string == '' or run_string.startswith('.'):
            return SANSUtility.WorkspaceDetails('', -1),True,'','', -1

        wkspname, run_no, logname, data_file = extract_workspace_name(run_string, is_trans, 
                                                            prefix=reducer.instrument.name(), 
                                                            run_number_width=reducer.instrument.run_number_width)

        if run_no == '':
            return SANSUtility.WorkspaceDetails('', -1),True,'','', -1

        if reload == False and mantid.workspaceExists(wkspname):
            return WorkspaceDetails(wkspname, shortrun_no),False,'','', -1

        filename = os.path.join(reducer._data_path, data_file)
        # Workaround so that the FileProperty does the correct searching of data paths if this file doesn't exist
        if not os.path.exists(filename):
            filename = data_file
        if period <= 0:
            period = 1
        if is_trans:
            try:
                if reducer.instrument.name() == 'SANS2D' and int(run_no) < 568:
                    dimension = SANSUtility.GetInstrumentDetails(reducer.instrument)[0]
                    specmin = dimension*dimension*2
                    specmax = specmin + 4
                else:
                    specmin = None
                    specmax = 8

                loader = LoadRun(filename, spec_min=specmin, spec_max=specmax, period=period)
                [filepath, wkspname, nPeriods] = loader.execute(reducer, wkspname)
            except RuntimeError, err:
                mantid.sendLogMessage("::SANS::Warning: "+str(err))
                return SANSUtility.WorkspaceDetails('', -1),True,'','', -1
        else:
            try:
                loader = LoadRun(filename, spec_min=None, spec_max=None, period=period)
                [filepath, wkspname, nPeriods] = loader.execute(reducer, wkspname)
            except RuntimeError, details:
                mantid.sendLogMessage("::SANS::Warning: "+str(details))
                return SANSUtility.WorkspaceDetails('', -1),True,'','', -1

        inWS = SANSUtility.WorkspaceDetails(wkspname, run_no)
        
        return inWS,True, reducer.instrument.name() + logname, filepath, nPeriods

    def _leaveSinglePeriod(self, groupW, period):
        #get the name of the individual workspace in the group
        oldName = groupW.getName()+'_'+str(period)
        #move this workspace out of the group (this doesn't delete it)
        groupW.remove(oldName)
    
        discriptors = groupW.getName().split('_')       #information about the run (run number, if it's 1D or 2D, etc) is listed in the workspace name between '_'s
        for i in range(0, len(discriptors) ):           #insert the period name after the run number
            if i == 0 :                                 #the run number is the first part of the name
                newName = discriptors[0]+'p'+str(period)#so add the period number here
            else :
                newName += '_'+discriptors[i]
    
        RenameWorkspace(oldName, newName)
    
        #remove the rest of the group
        mantid.deleteWorkspace(groupW.getName())
        return newName
    
    def _clearPrevious(self, inWS, others = []):
        if inWS != None:
            if type(inWS) == SANSUtility.WorkspaceDetails:
                inWS = inWS.getName()
            if mantid.workspaceExists(inWS) and (not inWS in others):
                mantid.deleteWorkspace(inWS)
                
class LoadTransmissions(SANSReductionSteps.BaseTransmission, LoadRun):
    """
        Transmission calculation for ISIS SANS instruments
    """
    # Transmission sample parameters
    _direct_sample = None
    _trans_sample = None
    _sample_reload = True
    _sample_period = -1
    
    # Transmission can parameters
    _direct_can = None
    _trans_can = None
    _can_reload = True
    _can_period = -1
    
    TRANS_SAMPLE = '' 
    DIRECT_SAMPLE = ''
    TRANS_SAMPLE_N_PERIODS = -1
    DIRECT_SAMPLE_N_PERIODS = -1
    TRANS_CAN = ''
    DIRECT_CAN = ''
    TRANS_CAN_N_PERIODS = -1
    DIRECT_CAN_N_PERIODS = -1
    
    def __init__(self):
        """
        """
        super(LoadTransmissions, self).__init__()
    
    def set_trans_sample(self, sample, direct, reload=True, period=-1):            
        self._trans_sample = sample
        self._direct_sample = direct
        self._sample_reload = reload
        self._sample_period = period
        
    def set_trans_can(self, can, direct, reload = True, period = -1):
        self._trans_can = can
        self._direct_can = direct
        self._can_reload = reload
        self._can_period = period
    
    def execute(self, reducer, workspace):
        # Load transmission sample
        self._clearPrevious(self.TRANS_SAMPLE)
        self._clearPrevious(self.DIRECT_SAMPLE)
        
        if self._trans_sample not in [None, '']:
            trans_ws, dummy1, dummy2, dummy3, self.TRANS_SAMPLE_N_PERIODS = \
                self._assignHelper(reducer, self._trans_sample, True, self._sample_reload, self._sample_period)
            self.TRANS_SAMPLE = trans_ws.getName()
        
        if self._direct_sample not in [None, '']:
            direct_sample_ws, dummy1, dummy2, dummy3, self.DIRECT_SAMPLE_N_PERIODS = \
                self._assignHelper(reducer, self._direct_sample, True, self._sample_reload, self._sample_period)
            self.DIRECT_SAMPLE = direct_sample_ws.getName()
        
        # Load transmission can
        self._clearPrevious(self.TRANS_CAN)
        self._clearPrevious(self.DIRECT_CAN)
    
        if self._trans_can not in [None, '']:
            can_ws, dummy1, dummy2, dummy3, self.TRANS_CAN_N_PERIODS = \
                self._assignHelper(reducer, self._trans_can, True, self._can_reload, self._can_period)
            self.TRANS_CAN = can_ws.getName()
            
        if self._direct_can in [None, '']:
            self.DIRECT_CAN, self.DIRECT_CAN_N_PERIODS = self.DIRECT_SAMPLE, self.DIRECT_SAMPLE_N_PERIODS
        else:
            direct_can_ws, dummy1, dummy2, dummy3, self.DIRECT_CAN_N_PERIODS = \
                self._assignHelper(reducer, self._direct_can, True, self._can_reload, self._can_period)
            self.DIRECT_CAN = direct_can_ws.getName()
 
class CanSubtraction(LoadRun):
    """
        Subtract the can after correcting it.
        Note that in the original SANSReduction.py, the can run was loaded immediately after
        the AssignCan() command was called. Since the loading needs information from the instrument, 
        we load only before doing the subtraction.
    """

    SCATTER_CAN = None
    _CAN_SETUP = None
    _CAN_RUN = None
    _CAN_N_PERIODS = -1
    #TODO: we don't need a dictionary here
    PERIOD_NOS = { "SCATTER_SAMPLE":1, "SCATTER_CAN":1 }

    def __init__(self, can_run, reload = True, period = -1):
        """
            @param lambda_min: MinWavelength parameter for CalculateTransmission
            @param lambda_max: MaxWavelength parameter for CalculateTransmission
            @param fit_method: FitMethod parameter for CalculateTransmission (Linear or Log)
        """
        super(CanSubtraction, self).__init__()
        self._can_run = can_run
        self._can_run_reload = reload
        self._can_run_period = period

    def _assign_can(self, reducer, can_run, reload = True, period = -1):
        #TODO: get rid of any reference to the instrument object as much as possible
        # Definitely get rid of the if-statements checking the instrument name.
        if not issubclass(reducer.instrument.__class__, SANSInsts.ISISInstrument):
            raise RuntimeError, "Transmission.assign_can expects an argument of class ISISInstrument"
        
        
        # Code from AssignCan
        self._clearPrevious(self.SCATTER_CAN)
        
        self._CAN_N_PERIODS = -1
        
        if( can_run.startswith('.') or can_run == '' or can_run == None):
            self.SCATTER_CAN.reset()
            self._CAN_RUN = ''
            self._CAN_SETUP = None
            return '', '()'
    
        self._CAN_RUN = can_run
        self.SCATTER_CAN ,reset, logname,filepath, self._CAN_N_PERIODS = \
            self._assignHelper(reducer, can_run, False, reload, period)
        if self.SCATTER_CAN.getName() == '':
            mantid.sendLogMessage('::SANS::Warning: Unable to load sans can run, cannot continue.')
            return '','()'
        if reset == True:
            self._CAN_SETUP  = None
            

        try:
            logvalues = reducer.instrument.load_detector_logs(logname,filepath)
            if logvalues == None:
                _issueWarning("Can logs could not be loaded, using sample values.")
                return self.SCATTER_CAN.getName(), "()"
        except AttributeError:
            if not reducer.instrument.name() == 'LOQ' : raise
    
        self.PERIOD_NOS["SCATTER_CAN"] = period
    
        if (reducer.instrument.name() == 'LOQ'):
            return self.SCATTER_CAN.getName(), ""
        
        smp_values = []
        front_det = reducer.instrument.getDetector('front')
        smp_values.append(reducer.instrument.FRONT_DET_Z + front_det.z_corr)
        smp_values.append(reducer.instrument.FRONT_DET_X + front_det.x_corr)
        smp_values.append(reducer.instrument.FRONT_DET_ROT + front_det.rot_corr)
        rear_det = reducer.instrument.getDetector('rear')
        smp_values.append(reducer.instrument.REAR_DET_Z + rear_det.z_corr)
        smp_values.append(reducer.instrument.REAR_DET_X + rear_det.x_corr)
    
        # Check against sample values and warn if they are not the same but still continue reduction
        if len(logvalues) == 0:
            return  self.SCATTER_CAN.getName(), logvalues
        
        can_values = []
        can_values.append(float(logvalues['Front_Det_Z']) + front_det.z_corr)
        can_values.append(float(logvalues['Front_Det_X']) + front_det.x_corr)
        can_values.append(float(logvalues['Front_Det_Rot']) + front_det.rot_corr)
        can_values.append(float(logvalues['Rear_Det_Z']) + rear_det.z_corr)
        can_values.append(float(logvalues['Rear_Det_X']) + rear_det.x_corr)
    
    
        det_names = ['Front_Det_Z', 'Front_Det_X','Front_Det_Rot', 'Rear_Det_Z', 'Rear_Det_X']
        for i in range(0, 5):
            if math.fabs(smp_values[i] - can_values[i]) > 5e-04:
                mantid.sendLogMessage("::SANS::Warning: values differ between sample and can runs. Sample = " + str(smp_values[i]) + \
                                  ' , Can = ' + str(can_values[i]))
                reducer.instrument.append_marked(det_names[i])
        # End of AssignCan code
        
        return self.SCATTER_CAN.getName(), logvalues

    def execute(self, reducer, workspace):
        """
        """ 
        if self._can_run is not None:
            self._assign_can(reducer, self._can_run, reload = self._can_run_reload, period = self._can_run_period)
        
        # Apply same corrections as for data then subtract from data
        # Start of WaveRangeReduction code
        # _initReduction code
        # _init_run()
        beamcoords = reducer._beam_finder.get_beam_center()

        final_ws = "can_temp_workspace"

        # Put the components in the correct positions
        currentDet = reducer.instrument.cur_detector().name() 
        maskpt_rmin, maskpt_rmax = reducer.instrument.set_component_positions(self.SCATTER_CAN.getName(), beamcoords[0], beamcoords[1])
        mantid.sendLogMessage('::SANS:: Initialized can workspace to [' + str(beamcoords[0]) + ',' + str(beamcoords[1]) + ']' )

        # Create a run details object
        TRANS_CAN = ''
        DIRECT_CAN = ''
        if reducer._transmission_calculator is not None:
            TRANS_CAN = reducer._transmission_calculator.TRANS_CAN
        if reducer._transmission_calculator is not None:
            DIRECT_CAN = reducer._transmission_calculator.DIRECT_CAN
            
        finding_centre = False
        
        
        tmp_smp = workspace+"_sam_tmp"
        RenameWorkspace(workspace, tmp_smp)
        # Run correction function
        # was  Correct(SCATTER_CAN, can_setup[0], can_setup[1], wav_start, wav_end, can_setup[2], can_setup[3], finding_centre)
        tmp_can = workspace+"_can_tmp_new"

        # Can correction
        #replaces Correct(can_setup, wav_start, wav_end, use_def_trans, finding_centre)
        reduce_can = copy.copy(reducer)
        #this will be the first command that is run in the new chain
        crop = reduce_can._reduction_steps.index(reduce_can.crop_detector)
        norm = reduce_can._reduction_steps.index(reduce_can.norm_mon)
        #stop before this current step
        end = reduce_can._reduction_steps.index(self)-1
        #some things are going to be changed, make deep copies of these
        reduce_can._data_files = copy.deepcopy(reducer._data_files)
        #set the workspace that we've been setting up as the one to be processed 
        reduce_can.set_process_single_workspace(self.SCATTER_CAN.getName())
        #the workspace is again branched with a new name
        reduce_can._reduction_steps = copy.deepcopy(reducer._reduction_steps)
        reduce_can._reduction_steps[crop] = CropDetBank(tmp_can)
        reduce_can._reduction_steps[norm]\
            = NormalizeToMonitor(raw_ws = self.SCATTER_CAN.getName())
        reduce_can.run_steps(start_ind=crop, stop_ind=end)
        
        #we now have the can workspace, use it
        Minus(tmp_smp, tmp_can, workspace)
    
#        if DEL__FINDING_CENTRE_:
#            mantid.deleteWorkspace(tmp_smp)
#            mantid.deleteWorkspace(tmp_can)
#            mantid.deleteWorkspace(workspace)        
#        else:
        #clean up the workspaces ready users to see them if required
        # Due to rounding errors, small shifts in detector encoders and poor stats in highest Q bins need "minus" the
        # workspaces before removing nan & trailing zeros thus, beware,  _sc,  _sam_tmp and _can_tmp may NOT have same Q bins
        ReplaceSpecialValues(InputWorkspace = tmp_smp,OutputWorkspace = tmp_smp, NaNValue="0", InfinityValue="0")
        ReplaceSpecialValues(InputWorkspace = tmp_can,OutputWorkspace = tmp_can, NaNValue="0", InfinityValue="0")
        if reducer.to_Q.output_type == '1D':
             rem_zeros = SANSReductionSteps.StripEndZeros()
             rem_zeros.execute(reducer, tmp_smp)
             rem_zeros.execute(reducer, tmp_can)
    
class Mask_ISIS(SANSReductionSteps.Mask):
    """
        Provides ISIS specific mask functionality (e.g. parsing
        MASK commands from user files), inherits from Mask
    """
    def __init__(self, timemask='', timemask_r='', timemask_f='', 
                 specmask='', specmask_r='', specmask_f='', both_dets=False):
        SANSReductionSteps.Mask.__init__(self)
        self._timemask=timemask 
        self._timemask_r=timemask_r
        self._timemask_f=timemask_f
        self._specmask=specmask
        self._specmask_r=specmask_r
        self._specmask_f=specmask_f
        self._lim_phi_xml = ''
        self._both_dets = both_dets
        
        ########################## Masking  ################################################
        # Mask the corners and beam stop if radius parameters are given

        self._min_radius = None
        self._max_radius = None

    def set_radi(self, min, max):
        self._min_radius = float(min)/1000.
        self._max_radius = float(max)/1000.

    def parse_instruction(self, details):
        """
            Parse an instruction line from an ISIS mask file
        """
        details = details.lstrip()
        details_compare = details.upper()
        if not details_compare.startswith('MASK'):
            _issueWarning('Ignoring malformed mask line ' + details)
            return
        
        parts = details_compare.split('/')
        # A spectrum mask or mask range applied to both detectors
        if len(parts) == 1:
            spectra = details[4:].lstrip()
            if len(spectra.split()) == 1:
                self._specmask += ',' + spectra
        elif len(parts) == 2:
            type = parts[1]
            detname = type.split()
            if type == 'CLEAR':
                self._specmask = ''
                self._specmask_r = ''
                self._specmask_f = ''
            elif type.startswith('T'):
                if type.startswith('TIME'):
                    bin_range = type[4:].lstrip()
                else:
                    bin_range = type[1:].lstrip()
                self._timemask += ';' + bin_range
            elif len(detname) == 2:
                det_type = detname[0]
                #TODO: warning: this means that Detector needs to be called before Mask
                if self.instrument.isDetectorName(det_type) :
                    spectra = detname[1]
                    if self.instrument.isHighAngleDetector(type) :
                        self._specmask_f += ',' + spectra
                    else:
                        self._specmask_r += ',' + spectra
                else:
                    _issueWarning('Detector \'' + det_type + '\' not found in currently selected instrument ' + self.instrument.name() + '. Skipping line.')
            else:
                _issueWarning('Unrecognized masking option "' + details + '"')
        elif len(parts) == 3:
            type = parts[1]
            if type == 'CLEAR':
                self._timemask = ''
                self._timemask_r = ''
                self._timemask_f = ''
            elif (type == 'TIME' or type == 'T'):
                parts = parts[2].split()
                if len(parts) == 3:
                    detname = parts[0].rstrip()
                    bin_range = parts[1].rstrip() + ' ' + parts[2].lstrip() 
                    if self.instrument.detectorExists(detname) :
                        if self.instrument.isHighAngleDetector(detname) :
                            self._timemask_f += ';' + bin_range
                        else:
                            self._timemask_r += ';' + bin_range
                    else:
                        _issueWarning('Detector \'' + det_type + '\' not found in currently selected instrument ' + self.instrument.name() + '. Skipping line.')
                else:
                    _issueWarning('Unrecognized masking option "' + details + '"')
        else:
            pass

    def _ConvertToSpecList(self, maskstring, detector):
        '''
            Convert a mask string to a spectra list
            6/8/9 RKH attempt to add a box mask e.g.  h12+v34 (= one pixel at intersection), h10>h12+v101>v123 (=block 3 wide, 23 tall)
        '''
        #Compile spectra ID list
        if maskstring == '':
            return ''
        masklist = maskstring.split(',')
        
        speclist = ''
        for x in masklist:
            x = x.lower()
            if '+' in x:
                bigPieces = x.split('+')
                if '>' in bigPieces[0]:
                    pieces = bigPieces[0].split('>')
                    low = int(pieces[0].lstrip('hv'))
                    upp = int(pieces[1].lstrip('hv'))
                else:
                    low = int(bigPieces[0].lstrip('hv'))
                    upp = low
                if '>' in bigPieces[1]:
                    pieces = bigPieces[1].split('>')
                    low2 = int(pieces[0].lstrip('hv'))
                    upp2 = int(pieces[1].lstrip('hv'))
                else:
                    low2 = int(bigPieces[1].lstrip('hv'))
                    upp2 = low2            
                if 'h' in bigPieces[0] and 'v' in bigPieces[1]:
                    ydim=abs(upp-low)+1
                    xdim=abs(upp2-low2)+1
                    speclist += detector.spectrum_block(low, low2,ydim, xdim) + ','
                elif 'v' in bigPieces[0] and 'h' in bigPieces[1]:
                    xdim=abs(upp-low)+1
                    ydim=abs(upp2-low2)+1
                    speclist += detector.spectrum_block(low2, low,nstrips, 'all')+ ','
                else:
                    print "error in mask, ignored:  " + x
            elif '>' in x:
                pieces = x.split('>')
                low = int(pieces[0].lstrip('hvs'))
                upp = int(pieces[1].lstrip('hvs'))
                if 'h' in pieces[0]:
                    nstrips = abs(upp - low) + 1
                    speclist += detector.spectrum_block(low, 0,nstrips, 'all')  + ','
                elif 'v' in pieces[0]:
                    nstrips = abs(upp - low) + 1
                    speclist += detector.spectrum_block(0,low, 'all', nstrips)  + ','
                else:
                    for i in range(low, upp + 1):
                        speclist += str(i) + ','
            elif 'h' in x:
                speclist += detector.spectrum_block(int(x.lstrip('h')), 0,1, 'all') + ','
            elif 'v' in x:
                speclist += detector.spectrum_block(0,int(x.lstrip('v')), 'all', 1) + ','
            elif 's' in x:
                speclist += x.lstrip('s') + ','
            elif x == '':
                #empty entries are allowed
                pass
            else:
                raise SyntaxError('Problem reading a mask entry: %s' %x)
        
        return speclist.rpartition(',')[0]

    def _mask_phi(self, id, centre, phimin, phimax, use_mirror=True):
        '''
            Mask the detector bank such that only the region specified in the
            phi range is left unmasked
        '''
        # convert all angles to be between 0 and 360
        while phimax > 360 : phimax -= 360
        while phimax < 0 : phimax += 360
        while phimin > 360 : phimin -= 360
        while phimin < 0 : phimin += 360
        while phimax<phimin : phimax += 360
    
        #Convert to radians
        phimin = math.pi*phimin/180.0
        phimax = math.pi*phimax/180.0
        
        id = str(id)
        self._lim_phi_xml = (
            self._infinite_cylinder(id+'_plane1',centre, [math.cos(-phimin + math.pi/2.0),math.sin(-phimin + math.pi/2.0),0])
            + self._infinite_cylinder(id+'_plane2',centre, [-math.cos(-phimax + math.pi/2.0),-math.sin(-phimax + math.pi/2.0),0])
            + self._infinite_cylinder(id+'_plane3',centre, [math.cos(-phimax + math.pi/2.0),math.sin(-phimax + math.pi/2.0),0])
            + self._infinite_cylinder(id+'_plane4',centre, [-math.cos(-phimin + math.pi/2.0),-math.sin(-phimin + math.pi/2.0),0]))
        
        if use_mirror : 
            self._lim_phi_xml += '<algebra val="#((pla pla2):(pla3 pla4))" />'
        else:
            #the formula is different for acute verses obstruse angles
            if phimax-phimin > math.pi :
              # to get an obtruse angle, a wedge that's more than half the area, we need to add the semi-inifinite volumes
                self._lim_phi_xml += '<algebra val="#(pla:pla2)" />'
            else :
              # an acute angle, wedge is more less half the area, we need to use the intesection of those semi-inifinite volumes
                self._lim_phi_xml += '<algebra val="#(pla pla2)" />'

    def _normalizePhi(self, phi):
        if phi > 90.0:
            phi -= 180.0
        elif phi < -90.0:
            phi += 180.0
        else:
            pass
        return phi

    def set_phi_limit(self, phimin, phimax, phimirror):
        if phimirror :
            if phimin > phimax:
                phimin, phimax = phimax, phimin
            if abs(phimin) > 180.0 :
                phimin = -90.0
            if abs(phimax) > 180.0 :
                phimax = 90.0
        
            if phimax - phimin == 180.0 :
                phimin = -90.0
                phimax = 90.0
            else:
                phimin = self.normalizePhi(phimin)
                phimax = self.normalizePhi(phimax)
    
        self._mask_phi('unique phi', [0,0,0], phimin,phimax,phimirror)

    def execute(self, reducer, workspace):
        #set up the spectra lists and shape xml to mask
        detector = reducer.instrument.cur_detector()
        if self._both_dets or detector.isAlias('rear'):
            rear = reducer.instrument.getDetector('rear')
            self.spec_list = self._ConvertToSpecList(self._specmask_r, rear)
            #masking for both detectors
            self.spec_list += self._ConvertToSpecList(self._specmask, rear)
            #Time mask
            SANSUtility.MaskByBinRange(workspace,self._timemask_r)
            SANSUtility.MaskByBinRange(workspace,self._timemask)

        if self._both_dets or detector.isAlias('front'):
            front = reducer.instrument.getDetector('front')
            #front specific masking
            self.spec_list += self._ConvertToSpecList(self._specmask_f, front)
            #masking for both detectors
            self.spec_list += self._ConvertToSpecList(self._specmask, front)
            #Time mask
            SANSUtility.MaskByBinRange(workspace,self._timemask_f)
            SANSUtility.MaskByBinRange(workspace,self._timemask)

        #reset the xml, as execute can be run more than once
        self._xml = []
        if DEL__FINDING_CENTRE_ == True:
            if ( not self._min_radius is None) and (self._min_radius > 0.0):
                self.add_cylinder(self._min_radius, self._maskpt_rmin[0], self._maskpt_rmin[1], 'center_find_beam_cen')
            if ( not self._max_radius is None) and (self._max_radius > 0.0):
                self.add_outside_cylinder(self._max_radius, self._maskpt_rmin[0], self._maskpt_rmin[1], 'center_find_beam_cen')
        else:
            xcenter = reducer.place_det_sam.maskpt_rmax[0]
            ycentre = reducer.place_det_sam.maskpt_rmax[1]
            if ( not self._min_radius is None) and (self._min_radius > 0.0):
                self.add_cylinder(self._min_radius, xcenter, ycentre, 'beam_stop')
            if ( not self._max_radius is None) and (self._max_radius > 0.0):
                self.add_outside_cylinder(self._max_radius, xcenter, ycentre, 'beam_area')
        #now do the masking
        SANSReductionSteps.Mask.execute(self, reducer, workspace)

        if self._lim_phi_xml != '':
            MaskDetectorsInShape(workspace, self._lim_phi_xml)
            
    def __str__(self):
        return '    radius', self.min_radius, self.max_radius+'\n'+\
            '    global spectrum mask: ', str(self._specmask)+'\n'+\
            '    rear spectrum mask: ', str(self._specmask_r)+'\n'+\
            '    front spectrum mask: ', str(self._specmask_f)+'\n'+\
            '    global time mask: ', str(self._timemask)+'\n'+\
            '    rear time mask: ', str(self._timemask_r)+'\n'+\
            '    front time mask: ', str(self._timemask_f)+'\n'


class LoadSample(LoadRun):
    """
    """
    #TODO: we don't need a dictionary here
    PERIOD_NOS = { "SCATTER_SAMPLE":1, "SCATTER_CAN":1 }

    def __init__(self, sample_run=None, reload=True, period=-1):
        super(LoadRun, self).__init__()
        self.SCATTER_SAMPLE = None
        self._SAMPLE_SETUP = None
        self._SAMPLE_RUN = None
        self._SAMPLE_N_PERIODS = -1
        self._sample_run = sample_run
        self._reload = reload
        self._period = period
        
        self.maskpt_rmin = None
        
        #This is set to the name of the workspace that was loaded, with some changes made to it 
        self.uncropped = None
    
    def set_options(self, reload=True, period=-1):
        self._reload = reload
        self._period = period
        
    def execute(self, reducer, workspace):
        # If we don't have a data file, look up the workspace handle
        if self._sample_run is None:
            self._sample_run = reducer._data_files.values()[0]
        # Code from AssignSample
        self._clearPrevious(self.SCATTER_SAMPLE)
        self._SAMPLE_N_PERIODS = -1
        
        if( self._sample_run.startswith('.') or self._sample_run == '' or self._sample_run == None):
            self._SAMPLE_SETUP = None
            self._SAMPLE_RUN = ''
            self.SCATTER_SAMPLE = None
            raise RunTimeError('Sample needs to be assigned as run_number.file_type')

        self.SCATTER_SAMPLE, reset, logname, filepath, self._SAMPLE_N_PERIODS = self._assignHelper(reducer, self._sample_run, False, self._reload, self._period)
        if self.SCATTER_SAMPLE.getName() == '':
            raise RunTimeError('Unable to load SANS sample run, cannot continue.')
        if reset == True:
            self._SAMPLE_SETUP = None

        self.uncropped  = self.SCATTER_SAMPLE.getName()
        p_run_ws = mantid[self.uncropped]
        run_num = p_run_ws.getSampleDetails().getLogData('run_number').value()
        reducer.instrument.set_up_for_sample(run_num)

        try:
            logvalues = reducer.instrument.load_detector_logs(logname,filepath)
            if logvalues == None:
                mantid.deleteWorkspace(self.SCATTER_SAMPLE.getName())
                raise RunTimeError('Sample logs cannot be loaded, cannot continue')
        except AttributeError:
            if not reducer.instrument.name() == 'LOQ': raise
        
        self.PERIOD_NOS["SCATTER_SAMPLE"] = self._period
        
        # Create a run details object
        TRANS_SAMPLE = ''
        DIRECT_SAMPLE = ''
        if reducer._transmission_calculator is not None:
            TRANS_SAMPLE = reducer.trans_loader.TRANS_SAMPLE
        if reducer._transmission_calculator is not None:
            DIRECT_SAMPLE = reducer.trans_loader.DIRECT_SAMPLE

        reducer.wksp_name = self.uncropped


class MoveComponents(ReductionStep):
    def __init__(self):
        #TODO: data_file = None only makes sense when AppendDataFile is used... (AssignSample?)
        super(MoveComponents, self).__init__()

    def execute(self, reducer, workspace, rebin_alg = 'use default'):

        # Put the components in the correct positions
        beamcoords = reducer._beam_finder.get_beam_center()
        self.maskpt_rmin, self.maskpt_rmax = reducer.instrument.set_component_positions(workspace, beamcoords[0], beamcoords[1])
        mantid.sendLogMessage('::SANS:: Moved sample workspace to [' + str(self.maskpt_rmin)+','+str(self.maskpt_rmax) + ']' )

class CropDetBank(ReductionStep):
    """
        Takes the spectra range of the current detector from the instrument object
        and crops the input workspace to just those spectra. Supports optionally
        changing the name of the output workspace, which is more efficient than
        running clone workspace to do that
    """ 
    def __init__(self, name_change=None):
        """
            If a name is passed to this function this reduction step
            will branch to a new output workspace. The name could be
            GetOutputName object or a string
            @param name_change: an object that contains the new name
        """
        super(CropDetBank, self).__init__()
        self._name_object = name_change

    def execute(self, reducer, workspace, rebin_alg = 'use default'):
        out_name = workspace
        if not self._name_object is None:
            if type(self._name_object) is GetOutputName:
                out_name = self._name_object.name
            elif type(self._name_object) is str:
                out_name = self._name_object
            else:
                mantid.sendLogMessage('Could not get the name of the output workspace, the output workspace won\'t be renamed (wrong type passed to CropDetBank)')

        # Get the detector bank that is to be used in this analysis leave the complete workspace
        CropWorkspace(workspace, out_name,
            StartWorkspaceIndex = reducer.instrument.cur_detector().first_spec_num - 1,
            EndWorkspaceIndex = reducer.instrument.cur_detector().last_spec_num - 1)

        reducer.wksp_name = out_name

class UnitsConvert(ReductionStep):
    def __init__(self, units, w_low = None, w_step = None, w_high = None):
        #TODO: data_file = None only makes sense when AppendDataFile is used... (AssignSample?)
        super(UnitsConvert, self).__init__()
        self._units = units
        self.wav_low = w_low
        self.wav_high = w_high
        self.wav_step = w_step

    def execute(self, reducer, workspace, rebin_alg = 'use default'):
        ConvertUnits(workspace, workspace, self._units)
        
        if rebin_alg == 'use default':
            rebin_alg = 'Rebin' 
        rebin_com = rebin_alg+'(workspace, workspace, "'+self.get_rebin()+'")'
        eval(rebin_com)

    def get_rebin(self):
        return str(self.wav_low)+', ' + str(self.wav_step) + ', ' + str(self.wav_high)
    
    def set_rebin(self, w_low = None, w_step = None, w_high = None):
        if not w_low is None:
            self.wav_low = w_low
        if not w_step is None:
            self.wav_step = w_step
        if not w_high is None:
            self.wav_high = w_high

    def get_range(self):
        return str(self.wav_low)+'_'+str(self.wav_high)

    def set_range(self, w_low = None, w_high = None):
        self.set_rebin(w_low, None, w_high)

    def __str__(self):
        return '    Wavelength range: ' + self.get_rebin()

class ConvertToQ(ReductionStep):
    _OUTPUT_TYPES = {'1D' : 'Q1D', '2D': 'Qxy'}
    
    def __init__(self, type = '1D'):
        #TODO: data_file = None only makes sense when AppendDataFile is used... (AssignSample?)
        super(ConvertToQ, self).__init__()
        
        #this should be set to 1D or 2D
        self._output_type = None
        #the algorithm that corrosponds to the above choice
        self._Q_alg = None
        self.set_output_type(type)
        #if true gravity is taken into account in the Q1D calculation
        self._use_gravity = False
        
        self.error_est_1D = None
    
    def set_output_type(self, discript):
        self._Q_alg = self._OUTPUT_TYPES[discript]
        self._output_type = discript
        
    def get_output_type(self):
        return self._output_type

    output_type = property(get_output_type, set_output_type, None, None)

    def set_gravity(self, flag):
        if isinstance(flag, bool) or isinstance(flag, int):
            self._use_gravity = bool(flag)
        else:
            _issueWarning("Invalid GRAVITY flag passed, try True/False. Setting kept as " + str(self._use_gravity)) 
                   
    def execute(self, reducer, workspace):
        #Steve, I'm not sure this contains good error values 
        if self._Q_alg == 'Q1D':
            if self.error_est_1D is None:
                raise RuntimeError('Could not find the workspace containing error estimates')
            Q1D(workspace, self.error_est_1D, workspace, reducer.Q_REBIN, AccountForGravity=self._use_gravity)
            mtd.deleteWorkspace(self.error_est_1D)
            self.error_est_1D = None

        elif self._Q_alg == 'Qxy':
            Qxy(workspace, workspace, reducer.QXY2, reducer.DQXY)
            ReplaceSpecialValues(workspace, workspace, NaNValue="0", InfinityValue="0")
        else:
            raise NotImplementedError('The type of Q reduction hasn\'t been set, e.g. 1D or 2D')

    def __str__(self):
        return '    Q range: ' + reducer.Q_REBIN +'\n    QXY range: ' + reducer.QXY2+'-'+reducer.DQXY

class NormalizeToMonitor(SANSReductionSteps.Normalize):
    """
        This step performs background removal on the monitor spectrum
        used for normalization and, for LOQ runs, executes a LOQ specific
        correction. It's input workspace is copied and accessible later
        as prenomed 
    """
    def __init__(self, spectrum_number=None, raw_ws=None):
        if not spectrum_number is None:
            index_num = spectrum_number - 1
        else:
            index_num = None
        super(NormalizeToMonitor, self).__init__(index_num)
        self._raw_ws = raw_ws

    def execute(self, reducer, workspace):
        normalization_spectrum = self._normalization_spectrum 
        if normalization_spectrum is None:
            #the -1 converts from spectrum number to spectrum index
            normalization_spectrum = reducer.instrument.get_incident_mon()-1
        
        raw_ws = self._raw_ws
        if raw_ws is None:
            raw_ws = reducer.data_loader.uncropped

        mantid.sendLogMessage('::SANS::Normalizing to monitor ' + str(self._normalization_spectrum))
        # Get counting time or monitor
        norm_ws = workspace+"_normalization"
        norm_ws = 'Monitor'

        
        CropWorkspace(raw_ws, norm_ws,
                      StartWorkspaceIndex = normalization_spectrum, 
                      EndWorkspaceIndex   = normalization_spectrum)
    
        if reducer.instrument.name() == 'LOQ':
            RemoveBins(norm_ws, norm_ws, '19900', '20500',
                Interpolation="Linear")
        
        # Remove flat background
        if reducer.BACKMON_START != None and reducer.BACKMON_END != None:
            FlatBackground(norm_ws, norm_ws, StartX = reducer.BACKMON_START,
                EndX = reducer.BACKMON_END, WorkspaceIndexList = '0')
    
        #perform the sample conversion on the monitor spectrum as was applied to the workspace
        if reducer.instrument.is_interpolating_norm():
            rebin_alg = 'InterpolatingRebin'
        else :
            rebin_alg = 'use default'
        reducer.to_wavelen.execute(reducer, norm_ws, rebin_alg)

        # At this point need to fork off workspace name to keep a workspace containing raw counts
        reducer.to_Q.error_est_1D = 'to_delete_'+workspace+'_prenormed'
        RenameWorkspace(workspace, reducer.to_Q.error_est_1D)
        Divide(reducer.to_Q.error_est_1D, norm_ws, workspace)

        mantid.deleteWorkspace(norm_ws)

# Setup the transmission workspace
##
class CalculateTransmission(SANSReductionSteps.BaseTransmission):
        # Map input values to Mantid options
    TRANS_FIT_OPTIONS = {
        'YLOG' : 'Log',
        'STRAIGHT' : 'Linear',
        'CLEAR' : 'Off',
        # Add Mantid ones as well
        'LOG' : 'Log',
        'LINEAR' : 'Linear',
        'LIN' : 'Linear',
        'OFF' : 'Off'
    }  

    def __init__(self):
        super(CalculateTransmission, self).__init__()
        self._lambda_min = None
        self._lambda_max = None
        self._fit_method = 'Log'
        self._use_full_range = True
    

    def set_trans_fit(self, lambda_min=None, lambda_max=None, fit_method="Log"):
        self._lambda_min = lambda_min
        self._lambda_max = lambda_max
        fit_method = fit_method.upper()
        if fit_method in self.TRANS_FIT_OPTIONS.keys():
            self._fit_method = self.TRANS_FIT_OPTIONS[fit_method]
        else:
            self._fit_method = 'Log'      
            mantid.sendLogMessage("ISISReductionStep.Transmission: Invalid fit mode passed to TransFit, using default LOG method")

    def set_full_wav(self, is_full):
        self._use_full_range = is_full

    def execute(self, reducer, workspace):
        if self._lambda_max == None:
            self._lambda_max = reducer.instrument.TRANS_WAV1_FULL
        if self._lambda_min == None:
            self._lambda_min = reducer.instrument.TRANS_WAV2_FULL
        
        trans_raw = run_setup.getTransRaw()
        direct_raw = run_setup.getDirectRaw()
        if trans_raw == '' or direct_raw == '':
            return None
    
        if self._use_full_range:
            wavbin = str(TRANS_WAV1_FULL) 
            wavbin = + ',' + str(ReductionSingleton().to_wavelen.wav_step)
            wavbin = + ',' + str(TRANS_WAV2_FULL)
            translambda_min = TRANS_WAV1_FULL
            translambda_max = TRANS_WAV2_FULL
        else:
            translambda_min = TRANS_WAV1
            translambda_max = TRANS_WAV2
            wavbin = str(Reducer.to_wavelen.get_rebin())
    
        fittedtransws = trans_raw.split('_')[0] + '_trans_' + run_setup.getSuffix() + '_' + str(translambda_min) + '_' + str(translambda_max)
        unfittedtransws = fittedtransws + "_unfitted"
        if use_def_trans == False or \
        (TRANS_FIT != 'Off' and mantid.workspaceExists(fittedtransws) == False) or \
        (TRANS_FIT == 'Off' and mantid.workspaceExists(unfittedtransws) == False):
            # If no fitting is required just use linear and get unfitted data from CalculateTransmission algorithm
            if TRANS_FIT == 'Off':
                fit_type = 'Linear'
            else:
                fit_type = TRANS_FIT
            #retrieve the user setting that tells us whether Rebin or InterpolatingRebin will be used during the normalisation 
            if reducer.instrument.name() == 'LOQ':
                # Change the instrument definition to the correct one in the LOQ case
                LoadInstrument(trans_raw, INSTR_DIR + "/LOQ_trans_Definition.xml")
                LoadInstrument(direct_raw, INSTR_DIR + "/LOQ_trans_Definition.xml")
                
                trans_tmp_out = SANSUtility.SetupTransmissionWorkspace(trans_raw,
                    '1,2', BACKMON_START, BACKMON_END, wavbin, 
                    reducer.instrument.use_interpol_trans_calc, True)
                
                direct_tmp_out = SANSUtility.SetupTransmissionWorkspace(direct_raw,
                    '1,2', BACKMON_START, BACKMON_END, wavbin,
                    reducer.instrument.use_interpol_trans_calc, True)
                
                CalculateTransmission(trans_tmp_out,direct_tmp_out, fittedtransws, MinWavelength = translambda_min, MaxWavelength =  translambda_max, \
                                      FitMethod = fit_type, OutputUnfittedData=True)
            else:
                trans_tmp_out = SANSUtility.SetupTransmissionWorkspace(trans_raw,
                    '1,2', BACKMON_START, BACKMON_END, wavbin,
                    reducer.instrument.use_interpol_trans_calc, False)
                
                direct_tmp_out = SANSUtility.SetupTransmissionWorkspace(direct_raw,
                    '1,2', BACKMON_START, BACKMON_END, wavbin,
                    reducer.instrument.use_interpol_trans_calc, False)
                
                CalculateTransmission(trans_tmp_out,direct_tmp_out, fittedtransws,
                    reducer.instrument.incid_mon_4_trans_calc, reducer.instrument.trans_monitor,
                    MinWavelength = translambda_min, MaxWavelength = translambda_max,
                    FitMethod = fit_type, OutputUnfittedData=True)
            # Remove temporaries
            mantid.deleteWorkspace(trans_tmp_out)
            mantid.deleteWorkspace(direct_tmp_out)
            
        if TRANS_FIT == 'Off':
            result = unfittedtransws
            mantid.deleteWorkspace(fittedtransws)
        else:
            result = fittedtransws
    
        if self.use_def_trans == DefaultTrans:
            tmp_ws = 'trans_' + run_setup.getSuffix() + '_' + reducer.to_wavelen.get_range()
            CropWorkspace(result, tmp_ws, XMin = str(reducer.to_wavelen.wav_low), XMax = str(reducer.to_wavelen.wav_high))
            trans_ws = tmp_ws
        else: 
            trans_ws = result

        Divide(workspace, trans_ws, workspace)

class ISISCorrections(SANSReductionSteps.CorrectToFileStep):
    def __init__(self, corr_type = '', operation = ''):
        super(ISISCorrections, self).__init__('', "Wavelength", "Divide")

        # Scaling values [%]
        self.rescale= 100.0
    
    def set_filename(self, filename):
        raise AttributeError('The correction must be set in the instrument, or use the CorrectionToFileStep instead')

    def execute(self, reducer, workspace):
        #use the instrument's correction file
        self._filename = reducer.instrument.cur_detector().correction_file
        #do the correct to file
        super(ISISCorrections, self).execute(reducer, workspace)

        scalefactor = self.rescale
        # Data reduced with Mantid is a factor of ~pi higher than colette.
        # For LOQ only, divide by this until we understand why.
        if reducer.instrument.name() == 'LOQ':
            rescaleToColette = math.pi
            scalefactor /= rescaleToColette

        ws = mantid[workspace]
        ws *= scalefactor

class ReadUserFile(ReductionStep):
    def __init__(self):
        """
            Reads a SANS mask file
        """
        super(ReadUserFile, self).__init__()
        self.filename = None

    def execute(self, reducer, workspace):
        if self.filename is None:
            raise LogicError('The user file must be set, use the function MaskFile')
        user_file = self.filename
        #Check that the file exists.
        if not os.path.isfile(user_file):
            user_file = os.path.join(reducer.user_file_path, self.filename)
            if not os.path.isfile(user_file):
                user_file = self._full_file_path(self.filename)
                if not os.path.isfile(user_file):
                    raise RuntimeError, "Cannot read mask. File path '%s' does not exist or is not in the user path." % filename
            
        # Re-initializes default values
        self._initialize_mask(reducer)
    
        file_handle = open(user_file, 'r')
        for line in file_handle:
            if line.startswith('!'):
                continue
            # This is so that I can be sure all EOL characters have been removed
            line = line.lstrip().rstrip()
            upper_line = line.upper()
            if upper_line.startswith('L/'):
                self._readLimitValues(line, reducer)
            
            elif upper_line.startswith('MON/'):
                self._readMONValues(line, reducer)
            
            elif upper_line.startswith('MASK'):
                reducer.mask.parse_instruction(upper_line)
            
            elif upper_line.startswith('SET CENTRE'):
                values = upper_line.split()
                reducer.set_beam_finder(SANSReductionSteps.BaseBeamFinder(float(values[2])/1000.0, float(values[3])/1000.0))
            
            elif upper_line.startswith('SET SCALES'):
                values = upper_line.split()
                reducer._corr_and_scale.rescale = float(values[2]) * 100.0
            
            elif upper_line.startswith('SAMPLE/OFFSET'):
                values = upper_line.split()
                reducer.instrument.set_sample_offset(values[1])
            
            elif upper_line.startswith('DET/'):
                det_specif = upper_line[4:]
                if det_specif.startswith('CORR'):
                    self._readDetectorCorrections(upper_line[8:], reducer)
                else:
                    # This checks whether the type is correct and issues warnings if it is not
                    reducer.instrument.setDetector(det_specif)
            
            elif upper_line.startswith('GRAVITY'):
                flag = upper_line[8:]
                if flag == 'ON':
                    reducer.to_Q.set_gravity(True)
                elif flag == 'OFF':
                    reducer.to_Q.set_gravity(False)
                else:
                    _issueWarning("Gravity flag incorrectly specified, disabling gravity correction")
                    reducer.to_Q.set_gravity(False)
            
            elif upper_line.startswith('BACK/MON/TIMES'):
                tokens = upper_line.split()
                if len(tokens) == 3:
                    reducer.BACKMON_START = int(tokens[1])
                    reducer.BACKMON_END = int(tokens[2])
                else:
                    _issueWarning('Incorrectly formatted BACK/MON/TIMES line, not running FlatBackground.')
                    reducer.BACKMON_START = None
                    reducer.BACKMON_END = None
            
            elif upper_line.startswith("FIT/TRANS/"):
                params = upper_line[10:].split()
                if len(params) == 3:
                    fit_type, lambdamin, lambdamax = params
                    if reducer.transmission_calculator is None:
                         reducer.transmission_calculator = CalculateTransmission()
                    reducer.transmission_calculator.set_trans_fit(lambda_min=lambdamin, 
                                                                lambda_max=lambdamax, 
                                                                fit_method=fit_type)
                else:
                    _issueWarning('Incorrectly formatted FIT/TRANS line, setting defaults to LOG and full range')
                    reducer.transmission_calculator = CalculateTransmission()
            
            else:
                continue
    
        # Close the handle
        file_handle.close()
        # Check if one of the efficency files hasn't been set and assume the other is to be used
        reducer.instrument.copy_correction_files()

        # Store the mask file within the final workspace so that it is saved to the CanSAS file
        if not workspace == '':
            AddSampleLog(workspace, "UserFile", self.filename)

    def _initialize_mask(self, reducer):
        self._restore_defaults(reducer)

        reducer.DEF_RMIN = None
        reducer.DEF_RMAX = None
       
        reducer.Q_REBIN = None
        reducer.QXY = None
        reducer.DQY = None
         
        reducer.BACKMON_END = None
        reducer.BACKMON_START = None

        reducer._corr_and_scale.rescale = 100.0

    # Read a limit line of a mask file
    def _readLimitValues(self, limit_line, reducer):
        limits = limit_line.split('L/')
        if len(limits) != 2:
            _issueWarning("Incorrectly formatted limit line ignored \"" + limit_line + "\"")
            return
        limits = limits[1]
        limit_type = ''
        if not ',' in limit_line:
            # Split with no arguments defaults to any whitespace character and in particular
            # multiple spaces are include
            elements = limits.split()
            if len(elements) == 4:
                limit_type, minval, maxval, step = elements[0], elements[1], elements[2], elements[3]
                rebin_str = None
                step_details = step.split('/')
                if len(step_details) == 2:
                    step_size = step_details[0]
                    step_type = step_details[1]
                    if step_type.upper() == 'LIN':
                        step_type = ''
                    else:
                        step_type = '-'
                else:
                    step_size = step_details[0]
                    step_type = ''
            elif len(elements) == 3:
                limit_type, minval, maxval = elements[0], elements[1], elements[2]
            else:
                # We don't use the L/SP line
                if not 'L/SP' in limit_line:
                    _issueWarning("Incorrectly formatted limit line ignored \"" + limit_line + "\"")
                    return
        else:
            limit_type = limits[0].lstrip().rstrip()
            rebin_str = limits[1:].lstrip().rstrip()
            minval = maxval = step_type = step_size = None
    
        if limit_type.upper() == 'WAV':
            reducer.to_wavelen.set_rebin(minval, step_type + step_size, maxval)
        elif limit_type.upper() == 'Q':
            if not rebin_str is None:
                reducer.Q_REBIN = rebin_str
            else:
                reducer.Q_REBIN = minval + "," + step_type + step_size + "," + maxval
        elif limit_type.upper() == 'QXY':
            reducer.QXY2 = float(maxval)
            reducer.DQXY = float(step_type + step_size)
        elif limit_type.upper() == 'R':
            reducer.mask.set_radi(minval, maxval)
            reducer.DEF_RMIN = float(minval)/1000.
            reducer.DEF_RMAX = float(maxval)/1000.
        elif limit_type.upper() == 'PHI':
            reducer.mask.set_phi_limit(float(minval), float(maxval), True) 
        elif limit_type.upper() == 'PHI/NOMIRROR':
            reducer.mask.set_phi_limit(float(minval), float(maxval), False)
        else:
            pass

    def _readMONValues(self, line, reducer):
        details = line[4:]
    
        #MON/LENTH, MON/SPECTRUM and MON/TRANS all accept the INTERPOLATE option
        interpolate = False
        interPlace = details.upper().find('/INTERPOLATE')
        if interPlace != -1 :
            interpolate = True
            details = details[0:interPlace]
    
        if details.upper().startswith('LENGTH'):
            reducer.suggest_monitor_spectrum(int(details.split()[1]), interpolate)
        
        elif details.upper().startswith('SPECTRUM'):
            reducer.set_monitor_spectrum(int(details.split('=')[1]), interpolate)
        
        elif details.upper().startswith('TRANS'):
            parts = details.split('=')
            if len(parts) < 2 or parts[0].upper() != 'TRANS/SPECTRUM' :
                _issueWarning('Unable to parse MON/TRANS line, needs MON/TRANS/SPECTRUM=')
            reducer.set_trans_spectrum(int(parts[1]), interpolate)        
    
        elif 'DIRECT' in details.upper() or details.upper().startswith('FLAT'):
            parts = details.split("=")
            if len(parts) == 2:
                filepath = parts[1].rstrip()
                if '[' in filepath:
                    idx = filepath.rfind(']')
                    filepath = filepath[idx + 1:]
                if not os.path.isabs(filepath):
                    filepath = os.path.join(reducer.user_file_path, filepath)
                type = parts[0]
                parts = type.split("/")
                if len(parts) == 1:
                    if parts[0].upper() == 'DIRECT':
                        reducer.instrument.cur_detector().correction_file \
                            = filepath
                        reducer.instrument.other_detector().correction_file \
                           = filepath
                    elif parts[0].upper() == 'HAB':
                        reducer.instrument.getDetector('HAB').correction_file \
                            = filepath
                    elif parts[0].upper() == 'FLAT':
                        reducer.flood_file =\
                            SANSReductionSteps.CorrectToFileStep(filepath, 'SpectrumNumber','Divide')
                    else:
                        pass
                elif len(parts) == 2:
                    detname = parts[1]
                    if detname.upper() == 'REAR':
                        reducer.instrument.getDetector('REAR').correction_file \
                            = filepath
                    elif detname.upper() == 'FRONT' or detname.upper() == 'HAB':
                        reducer.instrument.getDetector('FRONT').correction_file \
                            = filepath
                    else:
                        _issueWarning('Incorrect detector specified for efficiency file "' + line + '"')
                else:
                    _issueWarning('Unable to parse monitor line "' + line + '"')
            else:
                _issueWarning('Unable to parse monitor line "' + line + '"')

    def _readDetectorCorrections(self, details, reducer):
        values = details.split()
        det_name = values[0]
        det_axis = values[1]
        shift = float(values[2])
    
        detector = reducer.instrument.getDetector(det_name)
        if det_axis == 'X':
            detector.x_corr = shift
        elif det_axis == 'Y':
            detector.y_corr = shift
        elif det_axis == 'Z':
            detector.z_corr = shift
        elif det_axis == 'ROT':
            detector.rot_corr = shift
        else:
            raise NotImplemented('Detector correction on "'+det_axis+'" is not supported')


    def _restore_defaults(self, reducer):
        reducer.mask.parse_instruction('MASK/CLEAR')
        reducer.mask.parse_instruction('MASK/CLEAR/TIME')

        reducer.DEF_RMIN = reducer.DEF_RMAX
        reducer.Q_REBIN = reducer.QXY = reducer.DQY = None

        # Scaling values
        reducer._corr_and_scale.rescale = 100.  # percent
        
        reducer.BACKMON_START = reducer.BACKMON_END = None

class GetOutputName(ReductionStep):
    def __init__(self):
        """
            Reads a SANS mask file
        """
        super(GetOutputName, self).__init__()
        self.name = None

    def execute(self, reducer, workspace=None):
        """
            Generates the name of the sample workspace and changes the
            loaded workspace to that.
            @param reducer the reducer object that called this step
            @param workspace un-used
        """
        run = reducer._data_files.values()[0]
        self.name = run.split('.')[0]
        
        if (not reducer._period_num is None) and (reducer._period_num > 0):
            self.name += 'p'+str(reducer._period_num)
        self.name += reducer.instrument.cur_detector().name('short')
        self.name += '_' + reducer.to_Q.output_type
        self.name += '_' + reducer.to_wavelen.get_range()

class ReplaceErrors(ReductionStep):
    def __init__(self):
        super(ReplaceErrors, self).__init__()
        self.name = None

    def execute(self, reducer, workspace):
        ReplaceSpecialValues(InputWorkspace = workspace,OutputWorkspace = workspace, NaNValue="0", InfinityValue="0")


def extract_workspace_name(run_string, is_trans=False, prefix='', run_number_width=8):
    pieces = run_string.split('.')
    if len(pieces) != 2 :
         raise RuntimeError, "Invalid run specified: " + run_string + ". Please use RUNNUMBER.EXT format"
    else:
        run_no = pieces[0]
        ext = pieces[1]
    
    fullrun_no, logname, shortrun_no = _padRunNumber(run_no, run_number_width)

    if is_trans:
        wkspname =  shortrun_no + '_trans_' + ext.lower()
    else:
        wkspname =  shortrun_no + '_sans_' + ext.lower()
    
    return wkspname, run_no, logname, prefix+fullrun_no+'.'+ext

def _padRunNumber(run_no, field_width):
    nchars = len(run_no)
    digit_end = 0
    for i in range(0, nchars):
        if run_no[i].isdigit():
            digit_end += 1
        else:
            break
    
    if digit_end == nchars:
        filebase = run_no.rjust(field_width, '0')
        return filebase, filebase, run_no
    else:
        filebase = run_no[:digit_end].rjust(field_width, '0')
        return filebase + run_no[digit_end:], filebase, run_no[:digit_end]
