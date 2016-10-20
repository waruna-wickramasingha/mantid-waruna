from __future__ import (absolute_import, division, print_function)
import mantid.simpleapi as mantid

# --- Public API --- #


def focus(number, startup_object, ext="raw", fmode="trans", ttmode="TT70", atten=True, van_norm=True):
    # TODO support other extensions 
    return _run_pearl_focus(run_number=number, ext=ext, fmode=fmode, ttmode=ttmode, atten=atten, van_norm=van_norm,
                            instrument=startup_object)


def create_calibration_by_names(calruns, startup_objects, ngroupfile, ngroup="bank1,bank2,bank3,bank4"):
    _create_blank_cal_file(calibration_runs=calruns, user_input=startup_objects, group_names=ngroup,
                           instrument=startup_objects, out_grouping_file_name=ngroupfile)


def create_calibration(startup_object, calibration_runs, offset_file_path, grouping_file_path):
    _create_calibration(calibration_runs=calibration_runs, offset_file_path=offset_file_path,
                        grouping_file_path=grouping_file_path, instrument=startup_object)


def create_vanadium(startup_object, vanadium_runs, empty_runs, output_file_name, tt_mode="TT88",
                    num_of_spline_coefficients=60, do_absorp_corrections=True, generate_abosrp_corrections=False):
    _create_van(instrument=startup_object, van=vanadium_runs, empty=empty_runs, nvanfile=output_file_name,
                nspline=num_of_spline_coefficients, ttmode=tt_mode,
                absorb=do_absorp_corrections, gen_absorb=generate_abosrp_corrections)


def set_debug(debug_on=False):
    global g_debug
    g_debug = debug_on


def remove_intermediate_workspace(workspace_name):
    _remove_ws(ws_to_remove=workspace_name)

# --- Private Implementation --- #

# Please note these functions can change in any way at any time.
# For this reason please do not call them directly and instead use the Public API provided.

# If this doesn't quite provide what you need please let a developer know so we can create
# another API which will not change without notice


def _create_blank_cal_file(calibration_runs, out_grouping_file_name, instrument, user_input=None,
                           group_names="bank1,bank2,bank3,bank4"):

    cycle_information = instrument.get_cycle_information(calibration_runs)

    input_ws = _read_pearl_ws(calibration_runs, "raw", instrument)
    calibration_dspacing_ws = mantid.ConvertUnits(InputWorkspace=input_ws, Target="dSpacing")
    mantid.CreateCalFileByNames(InstrumentWorkspace=calibration_dspacing_ws,
                                GroupingFileName=out_grouping_file_name, GroupNames=group_names)
    remove_intermediate_workspace(calibration_dspacing_ws)
    remove_intermediate_workspace(input_ws)


def _create_calibration(calibration_runs, offset_file_path, grouping_file_path, instrument):
    input_ws = _read_pearl_ws(number=calibration_runs, ext="raw", instrument=instrument)
    cycle_information = instrument.get_cycle_information(calibration_runs)

    # TODO move these hard coded params to instrument specific
    if cycle_information["instrument_version"] == "new" or cycle_information["instrument_version"] == "new2":
        input_ws = mantid.Rebin(InputWorkspace=input_ws, Params="100,-0.0006,19950")

    d_spacing_cal = mantid.ConvertUnits(InputWorkspace=input_ws, Target="dSpacing")
    d_spacing_cal = mantid.Rebin(InputWorkspace=d_spacing_cal, Params="1.8,0.002,2.1")

    if cycle_information["instrument_version"] == "new2":
        cross_cor_ws = mantid.CrossCorrelate(InputWorkspace=d_spacing_cal, ReferenceSpectra=20,
                                             WorkspaceIndexMin=9, WorkspaceIndexMax=1063, XMin=1.8, XMax=2.1)

    elif cycle_information["instrument_version"] == "new":
        cross_cor_ws = mantid.CrossCorrelate(InputWorkspace=d_spacing_cal, ReferenceSpectra=20,
                                             WorkspaceIndexMin=9, WorkspaceIndexMax=943, XMin=1.8, XMax=2.1)
    else:
        cross_cor_ws = mantid.CrossCorrelate(InputWorkspace=d_spacing_cal, ReferenceSpectra=500,
                                             WorkspaceIndexMin=1, WorkspaceIndexMax=1440, XMin=1.8, XMax=2.1)

    # Ceo Cell refined to 5.4102(3) so 220 is 1.912795
    offset_output_path = mantid.GetDetectorOffsets(InputWorkspace=cross_cor_ws, Step=0.002, DReference=1.912795,
                                                   XMin=-200, XMax=200, GroupingFileName=offset_file_path)
    aligned_ws = mantid.AlignDetectors(InputWorkspace=input_ws, CalibrationFile=offset_file_path)
    cal_grouped_ws = mantid.DiffractionFocussing(InputWorkspace=aligned_ws, GroupingFileName=grouping_file_path)

    remove_intermediate_workspace(d_spacing_cal)
    remove_intermediate_workspace(cross_cor_ws)
    remove_intermediate_workspace(aligned_ws)
    remove_intermediate_workspace(cal_grouped_ws)


def _create_van(instrument, van, empty, nvanfile, ext="raw", ttmode="TT88", nspline=60, absorb=True, gen_absorb=False):


    # tt_mode set here will not be used within the function but instead when the PEARL_calibfiles()
    # is called it will return the correct tt_mode files.

    cycle_information = instrument.get_cycle_information(van)

    wvan = "wvan"

    input_van_ws = _read_pearl_ws(number=van, ext=ext, instrument=instrument)
    input_empty_ws = _read_pearl_ws(number=empty, ext=ext, instrument=instrument)

    corrected_van_ws = mantid.Minus(LHSWorkspace=input_van_ws, RHSWorkspace=input_empty_ws)

    remove_intermediate_workspace(input_empty_ws)
    remove_intermediate_workspace(input_van_ws)

    calibration_full_paths = instrument.get_calibration_full_paths(cycle=cycle_information["cycle"], in_tt_mode=ttmode)

    if absorb and not gen_absorb:
        corrected_van_ws = mantid.ConvertUnits(InputWorkspace=corrected_van_ws, Target="Wavelength")

        # TODO Change out name from T to something meaningful
        absorption_ws = mantid.LoadNexus(Filename=calibration_full_paths["vanadium_absorption"])
        corrected_van_ws = mantid.RebinToWorkspace(WorkspaceToRebin=corrected_van_ws, WorkspaceToMatch=absorption_ws)
        corrected_van_ws = mantid.Divide(LHSWorkspace=corrected_van_ws, RHSWorkspace=absorption_ws)
        remove_intermediate_workspace(ws_to_remove=absorption_ws)

    elif gen_absorb:
        mantid.CreateSampleShape(wvan, '<sphere id="sphere_1"> <centre x="0" y="0" z= "0" />\
                          <radius val="0.005" /> </sphere>')
        corrected_van_ws = \
            mantid.AbsorptionCorrection(InputWorkspace=corrected_van_ws, AttenuationXSection="5.08",
                                        ScatteringXSection="5.1", SampleNumberDensity="0.072",
                                        NumberOfWavelengthPoints="25", ElementSize="0.05")

        mantid.SaveNexus(Filename=calibration_full_paths["vanadium_absorption"],
                         InputWorkspace=corrected_van_ws, Append=False)

    corrected_van_ws = mantid.ConvertUnits(InputWorkspace=corrected_van_ws, Target="TOF")
    trange = "100,-0.0006,19990"  # TODO move this into instrument
    corrected_van_ws = mantid.Rebin(InputWorkspace=corrected_van_ws, Params=trange)

    corrected_van_ws = mantid.AlignDetectors(InputWorkspace=corrected_van_ws,
                                             CalibrationFile=calibration_full_paths["calibration"])

    focused_van_file = mantid.DiffractionFocussing(InputWorkspace=corrected_van_ws,
                                                   GroupingFileName=calibration_full_paths["grouping"])

    focused_van_file = mantid.ConvertUnits(InputWorkspace=focused_van_file, Target="TOF")
    trange = "150,-0.0006,19900"  # TODO move this into instrument
    focused_van_file = mantid.Rebin(InputWorkspace=focused_van_file, Params=trange)
    focused_van_file = mantid.ConvertUnits(InputWorkspace=focused_van_file, Target="dSpacing")

    remove_intermediate_workspace(ws_to_remove=corrected_van_ws)

    if cycle_information["instrument_version"] == "new2":
        splined_ws_list = _spline_new2_inst(focused_van_file, nspline)

        append = False
        for ws in splined_ws_list:
            mantid.SaveNexus(Filename=nvanfile, InputWorkspace=ws, Append=append)
            remove_intermediate_workspace(ws)
            append = True

    elif cycle_information["instrument_version"] == "new":
        van_stripped = mantid.ConvertUnits(InputWorkspace=focused_van_file, Target="dSpacing")

        # remove bragg peaks before spline

        #  TODO refactor this common code

        for i in range(0, 12):
            van_stripped = mantid.StripPeaks(InputWorkspace=van_stripped, FWHM=15, Tolerance=8, WorkspaceIndex=i)

        vam_stripped = mantid.ConvertUnits(InputWorkspace=van_stripped, Target="TOF")

        splined_ws_list = []
        for i in range(0, 12):
            out_ws_name = "_create_van_cal_spline-" + str(i)
            splined_ws_list.append(mantid.SplineBackground(InputWorkspace=vam_stripped, OutputWorkspace=out_ws_name,
                                                           WorkspaceIndex=i, NCoeff=nspline))

        append = False
        for ws in splined_ws_list:
            mantid.SaveNexus(Filename=nvanfile, InputWorkspace=ws, Append=append)
            remove_intermediate_workspace(ws)
            append = True

        remove_intermediate_workspace(van_stripped)

    elif cycle_information["instrument_version"] == "old":
        van_stripped = mantid.ConvertUnits(InputWorkspace=focused_van_file, Target="dSpacing")

        # remove bragg peaks before spline
        van_stripped = mantid.StripPeaks(InputWorkspace=van_stripped, FWHM=15, Tolerance=6, WorkspaceIndex=0)
        van_stripped = mantid.StripPeaks(InputWorkspace=van_stripped, FWHM=15, Tolerance=6, WorkspaceIndex=2)
        van_stripped = mantid.StripPeaks(InputWorkspace=van_stripped, FWHM=15, Tolerance=6, WorkspaceIndex=3)
        van_stripped = mantid.StripPeaks(InputWorkspace=van_stripped, FWHM=40, Tolerance=12, WorkspaceIndex=1)
        van_stripped = mantid.StripPeaks(InputWorkspace=van_stripped, FWHM=60, Tolerance=12, WorkspaceIndex=1)

        # Mask low d region that is zero before spline
        for reg in range(0, 4):
            if reg == 1:
                van_stripped = mantid.MaskBins(InputWorkspace=van_stripped, XMin=0, XMax=0.14, SpectraList=reg)
            else:
                van_stripped = mantid.MaskBins(InputWorkspace=van_stripped, XMin=0, XMax=0.06, SpectraList=reg)

        van_stripped = mantid.ConvertUnits(InputWorkspace=van_stripped,Target="TOF")

        splined_ws_list = []
        for i in range(0, 4):
            out_ws_name = "_create_van_calc_spline-" + str(i)
            if i == 1:
                coeff = 80
            else:
                coeff = 100
            splined_ws_list.append(mantid.SplineBackground(InputWorkspace=van_stripped, OutputWorkspace=out_ws_name,
                                                           WorkspaceIndex=i, NCoeff=coeff))

        append = False
        for ws in splined_ws_list:
            mantid.SaveNexus(Filename=nvanfile, InputWorkspace=van_stripped, Append=append)
            append = True
            remove_intermediate_workspace(ws)
    else:
        raise ValueError("Mode not known or supported")

    mantid.LoadNexus(Filename=nvanfile, OutputWorkspace="Van_data")


def _spline_new2_inst(focused_van_file, nspline):
    # remove bragg peaks before spline
    van_stripped_ws = mantid.StripPeaks(InputWorkspace=focused_van_file, FWHM=15, Tolerance=8, WorkspaceIndex=0)
    for i in range(1, 12):  # TODO remove this hardcoded value if possible - this is 14 with the 2 below
        van_stripped_ws = mantid.StripPeaks(InputWorkspace=van_stripped_ws, FWHM=15, Tolerance=8,
                                            WorkspaceIndex=i)

    # run twice on low angle as peaks are very broad
    for i in range(0, 2):
        van_stripped_ws = mantid.StripPeaks(InputWorkspace=van_stripped_ws, FWHM=100, Tolerance=10,
                                            WorkspaceIndex=12)
        van_stripped_ws = mantid.StripPeaks(InputWorkspace=van_stripped_ws, FWHM=60, Tolerance=10,
                                            WorkspaceIndex=13)
    van_stripped_ws = mantid.ConvertUnits(InputWorkspace=van_stripped_ws, Target="TOF")
    splined_ws_list = []
    for i in range(0, 14):
        out_ws_name = "_create_van_splined_ws-" + str(i + 1)
        splined_ws_list.append(mantid.SplineBackground(InputWorkspace=van_stripped_ws, OutputWorkspace=out_ws_name,
                                                       WorkspaceIndex=i, NCoeff=nspline))
    remove_intermediate_workspace(van_stripped_ws)
    return splined_ws_list


def _generate_cycle_dir(raw_data_dir, run_cycle):
    str_run_cycle = str(run_cycle)
    # Append current cycle to raw data directory
    generated_dir = raw_data_dir + str_run_cycle
    if raw_data_dir.endswith('\\'):
        generated_dir += '\\'
    elif raw_data_dir.endswith('/'):
        generated_dir += '/'
    else:
        raise ValueError("Path :" + raw_data_dir + "\n Does not end with a \\ or / character")
    return generated_dir


def _load_monitor(number, input_dir, instrument):
    _load_monitor_out_ws = None
    if isinstance(number, int):
        full_file_path = instrument.generate_input_full_path(run_number=number, input_dir=input_dir)
        mspectra = instrument.get_monitor_spectra(number)
        _load_monitor_out_ws = mantid.LoadRaw(Filename=full_file_path, SpectrumMin=mspectra, SpectrumMax=mspectra,
                                              LoadLogFiles="0")
    else:
        _load_monitor_out_ws = _load_monitor_sum_range(files=number, input_dir=input_dir, instrument=instrument)

    return _load_monitor_out_ws


def _load_monitor_sum_range(files, input_dir, instrument):
    loop = 0
    num = files.split("_")
    frange = list(range(int(num[0]), int(num[1]) + 1))
    mspectra = instrument.get_monitor_spectra(int(num[0]))
    out_ws = None
    for i in frange:
        file_path = instrument.generate_input_full_path(i, input_dir)
        outwork = "mon" + str(i)
        mantid.LoadRaw(Filename=file_path, OutputWorkspace=outwork, SpectrumMin=mspectra, SpectrumMax=mspectra,
                       LoadLogFiles="0")
        loop += 1
        if loop == 2:
            firstwk = "mon" + str(i - 1)
            secondwk = "mon" + str(i)
            out_ws = mantid.Plus(LHSWorkspace=firstwk, RHSWorkspace=secondwk)
            mantid.mtd.remove(firstwk)
            mantid.mtd.remove(secondwk)
        elif loop > 2:
            secondwk = "mon" + str(i)
            out_ws = mantid.Plus(LHSWorkspace=out_ws, RHSWorkspace=secondwk)
            mantid.mtd.remove(secondwk)

    return out_ws


def _load_raw_files(run_number, ext, instrument, input_dir):
    out_ws = None
    if isinstance(run_number, int):
        if ext[0] == 's':
            # TODO deal with liveData in higher class
            raise NotImplementedError()

        infile = instrument.generate_input_full_path(run_number=run_number, input_dir=input_dir)
        out_ws = mantid.LoadRaw(Filename=infile, LoadLogFiles="0")
    else:
        out_ws = _load_raw_file_range(run_number, input_dir, instrument)
    return out_ws


def _load_raw_file_range(files, input_dir, instrument):
    loop = 0
    num = files.split("_")
    frange = list(range(int(num[0]), int(num[1]) + 1))
    out_ws = None
    for i in frange:
        file_path = instrument.generate_input_full_path(i, input_dir)
        outwork = "run" + str(i)
        mantid.LoadRaw(Filename=file_path, OutputWorkspace=outwork, LoadLogFiles="0")
        loop += 1
        if loop == 2:
            firstwk = "run" + str(i - 1)
            secondwk = "run" + str(i)
            out_ws = mantid.Plus(LHSWorkspace=firstwk, RHSWorkspace=secondwk)
            mantid.mtd.remove(firstwk)
            mantid.mtd.remove(secondwk)
        elif loop > 2:
            secondwk = "run" + str(i)
            out_ws = mantid.Plus(LHSWorkspace=out_ws, RHSWorkspace=secondwk)
            mantid.mtd.remove(secondwk)
    return out_ws


def _read_pearl_ws(number, ext, instrument):
    raw_data_dir = instrument.raw_data_dir
    cycle_information = instrument.get_cycle_information(run_number=number)
    input_dir = _generate_cycle_dir(raw_data_dir, cycle_information["cycle"])
    input_ws = _load_raw_files(run_number=number, ext=ext, instrument=instrument, input_dir=input_dir)

    _read_pearl_workspace = mantid.ConvertUnits(InputWorkspace=input_ws, Target="Wavelength")
    _read_pearl_monitor = instrument.get_monitor(run_number=number, input_dir=input_dir, spline_terms=20)
    _read_pearl_workspace = mantid.NormaliseToMonitor(InputWorkspace=_read_pearl_workspace,
                                                      MonitorWorkspace=_read_pearl_monitor,
                                                      IntegrationRangeMin=0.6, IntegrationRangeMax=5.0)
    output_ws = mantid.ConvertUnits(InputWorkspace=_read_pearl_workspace, Target="TOF")

    remove_intermediate_workspace(_read_pearl_monitor)
    remove_intermediate_workspace(_read_pearl_workspace)
    return output_ws


def _run_pearl_focus(instrument, run_number, ext="raw", fmode="trans", ttmode="TT70", atten=True, van_norm=True):

    cycle_information = instrument.get_cycle_information(run_number=run_number)

    alg_range, save_range = instrument.get_instrument_alg_save_ranges(cycle_information["instrument_version"])

    input_file_paths = instrument.get_calibration_full_paths(cycle=cycle_information["cycle"], tt_mode=ttmode)

    output_file_names = instrument.generate_out_file_paths(run_number, instrument.output_dir)
    input_workspace = _read_pearl_ws(number=run_number, ext=ext, instrument=instrument)
    input_workspace = mantid.Rebin(InputWorkspace=input_workspace, Params=instrument.get_tof_binning())
    input_workspace = mantid.AlignDetectors(InputWorkspace=input_workspace, CalibrationFile=input_file_paths["calibration"])
    input_workspace = mantid.DiffractionFocussing(InputWorkspace=input_workspace, GroupingFileName=input_file_paths["grouping"])

    calibrated_spectra = _focus_load(alg_range, input_workspace, input_file_paths, instrument, van_norm)

    remove_intermediate_workspace(input_workspace)

    if fmode == "all":
        processed_nexus_files = _focus_mode_all(output_file_names, calibrated_spectra)

    elif fmode == "groups":
        processed_nexus_files = _focus_mode_groups(alg_range, cycle_information, output_file_names, save_range,
                                                   calibrated_spectra)

    elif fmode == "trans":

        processed_nexus_files = _focus_mode_trans(output_file_names, atten, instrument, calibrated_spectra)

    elif fmode == "mods":

        processed_nexus_files = _focus_mode_mods(output_file_names, calibrated_spectra)

    else:
        raise ValueError("Focus mode unknown")

    return processed_nexus_files


def _focus_mode_mods(output_file_names, calibrated_spectra):
    index = 1
    append = False
    output_list = []
    for ws in calibrated_spectra:

        if ws == calibrated_spectra[0]:
            # Skip WS group
            continue

        mantid.SaveGSS(InputWorkspace=ws, Filename=output_file_names["gss_filename"], Append=append, Bank=index)
        output_name = "_focus_mode_mods-" + str(index)
        dspacing_ws = mantid.ConvertUnits(InputWorkspace=ws, OutputWorkspace=output_name, Target="dSpacing")
        output_list.append(dspacing_ws)
        mantid.SaveNexus(Filename=output_file_names["nxs_filename"], InputWorkspace=dspacing_ws, Append=append)

        append = True
    return output_list


def _focus_mode_trans(output_file_names, atten, instrument, calibrated_spectra):
    summed_ws = mantid.CloneWorkspace(InputWorkspace=calibrated_spectra[1])
    for i in range(2, 10):  # Add workspaces 2-9
        summed_ws = mantid.Plus(LHSWorkspace=summed_ws, RHSWorkspace=calibrated_spectra[i])

    summed_ws = mantid.Scale(InputWorkspace=summed_ws, Factor=0.111111111111111)

    attenuated_workspace = summed_ws
    if atten:
        no_att = output_file_names["output_name"] + "_noatten"

        no_att_ws = mantid.CloneWorkspace(InputWorkspace=summed_ws, OutputWorkspace=no_att)
        attenuated_workspace = mantid.ConvertUnits(InputWorkspace=attenuated_workspace, Target="dSpacing")
        attenuated_workspace = instrument.attenuate_workspace(attenuated_workspace)
        attenuated_workspace = mantid.ConvertUnits(InputWorkspace=attenuated_workspace, Target="TOF")

    mantid.SaveGSS(InputWorkspace=attenuated_workspace, Filename=output_file_names["gss_filename"], Append=False, Bank=1)
    mantid.SaveFocusedXYE(InputWorkspace=attenuated_workspace, Filename=output_file_names["tof_xye_filename"],
                          Append=False, IncludeHeader=False)

    attenuated_workspace = mantid.ConvertUnits(InputWorkspace=attenuated_workspace, Target="dSpacing")
    mantid.SaveFocusedXYE(InputWorkspace=attenuated_workspace, Filename=output_file_names["dspacing_xye_filename"],
                          Append=False, IncludeHeader=False)
    mantid.SaveNexus(InputWorkspace=attenuated_workspace, Filename=output_file_names["nxs_filename"], Append=False)

    output_list = [attenuated_workspace]

    for i in range(1, 10):
        workspace_name = "_focus_mode_trans-dspacing" + str(i)
        to_save = mantid.ConvertUnits(InputWorkspace=calibrated_spectra[i], Target="dSpacing",
                                      OutputWorkspace=workspace_name)
        output_list.append(to_save)
        mantid.SaveNexus(Filename=output_file_names["nxs_filename"], InputWorkspace=to_save, Append=True)

    remove_intermediate_workspace(summed_ws)
    return output_list


def _focus_mode_groups(alg_range, cycle_information, output_file_names, save_range, calibrated_spectra):
    output_list = []
    to_save = _sum_groups_of_three_ws(calibrated_spectra)

    workspaces_4_to_9 = mantid.Plus(LHSWorkspace=to_save[1], RHSWorkspace=to_save[2])
    workspaces_4_to_9 = mantid.Scale(InputWorkspace=workspaces_4_to_9, Factor=0.5)
    to_save.append(workspaces_4_to_9)
    append = False
    index = 1
    for ws in to_save:
        if cycle_information["instrument_version"] == "new":
            mantid.SaveGSS(InputWorkspace=ws, Filename=output_file_names["gss_filename"], Append=append,
                           Bank=index)
        elif cycle_information["instrument_version"] == "new2":
            mantid.SaveGSS(InputWorkspace=ws, Filename=output_file_names["gss_filename"], Append=False,
                           Bank=index)

        workspace_names = "_focus_mode_groups_save-" + str(index)
        dspacing_ws = mantid.ConvertUnits(InputWorkspace=ws, OutputWorkspace=workspace_names, Target="dSpacing")
        output_list.append(dspacing_ws)
        mantid.SaveNexus(Filename=output_file_names["nxs_filename"], InputWorkspace=dspacing_ws, Append=append)
        append = True
        index += 1

    for i in range(0, save_range):
        workspace_names = "_focus_mode_groups_save-" + str(i + 9)

        tosave = calibrated_spectra[i + 9]

        mantid.SaveGSS(InputWorkspace=tosave, Filename=output_file_names["gss_filename"], Append=True, Bank=i + 5)

        output_list.append(mantid.ConvertUnits(InputWorkspace=tosave,
                                               OutputWorkspace=workspace_names, Target="dSpacing"))

        mantid.SaveNexus(Filename=output_file_names["nxs_filename"], InputWorkspace=tosave, Append=True)
    return output_list


def _sum_groups_of_three_ws(calibrated_spectra, ):
    workspace_list = []
    to_scale_list = []
    output_list = []
    for outer_loop_count in range(0, 3):
        # First clone workspaces 1/4/7
        pass_multiplier = (outer_loop_count * 3)
        first_ws_index = pass_multiplier + 1
        workspace_names = "focus_mode_groups-" + str(first_ws_index)
        workspace_list.append(mantid.CloneWorkspace(InputWorkspace=calibrated_spectra[first_ws_index],
                                                    OutputWorkspace=workspace_names))
        # Then add workspaces 1+2+3 / 4+5+6 / 7+8+9
        for i in range(2, 4):
            input_ws_index = i + pass_multiplier  # Workspaces 2/3
            inner_workspace_names = "focus_mode_groups-" + str(input_ws_index)

            to_scale_list.append(mantid.Plus(LHSWorkspace=workspace_list[outer_loop_count],
                                             RHSWorkspace=calibrated_spectra[input_ws_index],
                                             OutputWorkspace=inner_workspace_names))

        # Finally scale the output workspaces
        workspace_names = "focus_mode_groups_scaled-" + str(outer_loop_count)
        output_list.append(mantid.Scale(InputWorkspace=to_scale_list[outer_loop_count],
                                        OutputWorkspace=workspace_names, Factor=0.333333333333))
    for ws in to_scale_list:
        remove_intermediate_workspace(ws)
    return output_list


def _focus_mode_all(output_file_names, calibrated_spectra):
    first_spectrum = calibrated_spectra[0]
    summed_spectra = mantid.CloneWorkspace(InputWorkspace=first_spectrum)

    for i in range(1, 9):  # TODO why is this 1-8
        summed_spectra = mantid.Plus(LHSWorkspace=summed_spectra, RHSWorkspace=calibrated_spectra[i])

    summed_spectra = mantid.Scale(InputWorkspace=summed_spectra, Factor=0.111111111111111)
    mantid.SaveGSS(InputWorkspace=summed_spectra, Filename=output_file_names["gss_filename"], Append=False, Bank=1)

    summed_spectra = mantid.ConvertUnits(InputWorkspace=summed_spectra, Target="dSpacing")
    mantid.SaveNexus(Filename=output_file_names["nxs_filename"], InputWorkspace=summed_spectra, Append=False)

    output_list = []
    for i in range(0, 3):
        ws_to_save = calibrated_spectra[(i + 10)]  # Save out workspaces 10/11/12

        mantid.SaveGSS(InputWorkspace=ws_to_save, Filename=output_file_names["gss_filename"], Append=True, Bank=i + 2)
        to_save = mantid.ConvertUnits(InputWorkspace=ws_to_save, OutputWorkspace=ws_to_save, Target="dSpacing")
        output_list.append(to_save)
        mantid.SaveNexus(Filename=output_file_names["nxs_filename"], InputWorkspace=to_save, Append=True)

    return output_list


def _focus_load(alg_range, focused_ws, input_file_paths, instrument, van_norm):
    processed_spectra = []
    if van_norm:
        vanadium_ws_list = mantid.LoadNexus(Filename=input_file_paths["vanadium"])

    for index in range(0, alg_range):
        if van_norm:
            processed_spectra.append(calc_calibration_with_vanadium(focused_ws, index,
                                                                    vanadium_ws_list[index + 1], instrument))
        else:
            processed_spectra.append(calc_calibration_without_vanadium(focused_ws, index, instrument))

    if van_norm:
        remove_intermediate_workspace(vanadium_ws_list[0]) # Delete the WS group

    return processed_spectra


def calc_calibration_without_vanadium(focused_ws, index, instrument):
    focus_spectrum = mantid.ExtractSingleSpectrum(InputWorkspace=focused_ws, WorkspaceIndex=index)
    focus_spectrum = mantid.ConvertUnits(InputWorkspace=focus_spectrum, Target="TOF")
    focus_spectrum = mantid.Rebin(InputWorkspace=focus_spectrum, Params=instrument.tof_binning)
    focus_calibrated = mantid.CropWorkspace(InputWorkspace=focus_spectrum, XMin=0.1)
    return focus_calibrated


def calc_calibration_with_vanadium(focused_ws, index, vanadium_ws, instrument):
    # Load in workspace containing vanadium run
    van_rebinned = mantid.Rebin(InputWorkspace=vanadium_ws, Params=instrument.get_tof_binning())

    van_spectrum = mantid.ExtractSingleSpectrum(InputWorkspace=focused_ws, WorkspaceIndex=index)
    van_spectrum = mantid.ConvertUnits(InputWorkspace=van_spectrum, Target="TOF")
    van_spectrum = mantid.Rebin(InputWorkspace=van_spectrum, Params=instrument.get_tof_binning())

    van_processed = "van_processed" + str(index)  # Workaround for Mantid overwriting the WS in a loop
    mantid.Divide(LHSWorkspace=van_spectrum, RHSWorkspace=van_rebinned, OutputWorkspace=van_processed)
    mantid.CropWorkspace(InputWorkspace=van_processed, XMin=0.1, OutputWorkspace=van_processed)
    mantid.Scale(InputWorkspace=van_processed, Factor=10, OutputWorkspace=van_processed)

    remove_intermediate_workspace(van_rebinned)
    remove_intermediate_workspace(van_spectrum)

    return van_processed


def _remove_ws(ws_to_remove):
    """
    Removes any intermediate workspaces if debug is set to false
        @param ws_to_remove: The workspace to remove from the ADS
    """
    try:
        if not g_debug:
            _remove_ws_wrapper(ws=ws_to_remove)
    except NameError:  # If g_debug has not been set
        _remove_ws_wrapper(ws=ws_to_remove)


def _remove_ws_wrapper(ws):
    mantid.DeleteWorkspace(ws)
    del ws  # Mark it as deleted so that Python can throw before Mantid preserving more information