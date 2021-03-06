from glob import glob
import os

import nibabel as nb
import numpy as np
import pandas as pd

from lhab_pipelines.utils import to_tsv, read_tsv, add_info_to_json


# subject and session id related
def get_clean_subject_id(old_subject_id):
    "lhab_1234 -> lhab1234"
    return old_subject_id[:4] + old_subject_id[5:]


def get_clean_ses_id(old_ses_id):
    "T1 -> tp1"
    return "tp" + old_ses_id[1:]


def get_public_sub_id(old_sub_id, lut_file, from_col="old_id", to_col="new_id"):
    """returns public sub_id of style lhabX0001
    if old_subj_id is string: returns string
    if old_subj_id is list: returns list """
    df = pd.read_csv(lut_file, sep="\t")
    df = df.set_index(from_col)
    if isinstance(old_sub_id, str):
        return df.loc[old_sub_id].values[0]
    else:
        out_list = df.loc[old_sub_id, to_col].tolist()
        assert len(out_list) == len(old_sub_id), "In and out list not the same length %s, %s" % (out_list, old_sub_id)
        return out_list


def get_private_sub_id(new_sub_id, lut_file):
    """returns private sub_id of style lhab_0001
    if new_sub_id is string: returns string
    if new_sub_id is list: returns list """
    df = pd.read_csv(lut_file, sep="\t")
    df = df.set_index("new_id")
    if isinstance(new_sub_id, str):
        return df.loc[new_sub_id].values[0]
    else:
        out_list = df.loc[new_sub_id].iloc[:, 0].tolist()
        assert len(out_list) == len(new_sub_id), "In and out list not the same length %s, %s" % (out_list, new_sub_id)
        return out_list


# BIDS related IO
def add_additional_bids_parameters_from_par(par_file, bids_file, parameters={"angulation": "Angulation"}):
    header_params = {}
    for param, param_label in parameters.items():
        header_params[param_label] = get_par_info(par_file, param)[param]  # out_parameter
    add_info_to_json(bids_file, header_params)


def add_flip_angle_from_par(par_file, bids_file):
    general_info, image_defs = read_par(par_file)
    add_info_to_json(bids_file, {"FlipAngle": image_defs["image_flip_angle"][0]})


def add_total_readout_time_from_par(par_file, bids_file):
    general_info, image_defs = read_par(par_file)
    wfs = general_info["water_fat_shift"]
    ef = general_info["epi_factor"]
    if ef != 1:  # ef=1: no EPI --> trt not meaningful
        es = wfs / (434.215 * (ef + 1))  # echo spacing in sec
        trt = es * (ef - 1)  # in sec
        add_info_to_json(bids_file, {"TotalReadoutTime": trt, "EffectiveEchoSpacing": es})


def update_sub_scans_file(output_dir, bids_sub, bids_ses, bids_modality, out_filename, par_file, public_output=True):
    """
    one file per subject with
    -ses id
    -filename
    -if not public: date of acquisition
    """
    general_info, image_defs = read_par(par_file)
    acq_time = parse_acq_time(general_info)

    scans_file = os.path.join(output_dir, bids_sub, bids_sub + "_scans.tsv")
    if os.path.exists(scans_file):
        scans = read_tsv(scans_file)
    else:
        scans = pd.DataFrame([])
    scans = scans.append(
        {"participant_id": bids_sub, "session_id": bids_ses,
         "filename": bids_ses + "/" + bids_modality + "/" + out_filename + ".nii.gz",
         "acq_time": acq_time}, ignore_index=True)
    if not public_output:
        scans = scans[["participant_id", "session_id", "filename", "acq_time"]]
    else:
        scans = scans[["participant_id", "session_id", "filename"]]
    to_tsv(scans, scans_file)


def get_image_acq(par_files):
    df = pd.DataFrame()
    for par in par_files:
        general_info, image_defs = read_par(par)
        acq_time = parse_acq_time(general_info)
        df = df.append(pd.DataFrame({"file": [par], "acq_time": [acq_time]}))
    return df


# PAR IO
def read_par(par_file):
    with open(par_file, "r") as fi:
        version, gen_dict, image_lines = nb.parrec._split_header(fi)
        general_info = _process_gen_dict(gen_dict)
        image_defs = nb.parrec._process_image_lines(image_lines, version)
    return general_info, image_defs


def get_par_info(par_file, parameters):
    from collections import OrderedDict
    if not isinstance(parameters, list):
        parameters = [parameters]
    out_parameters = OrderedDict()
    general_info, image_defs = read_par(par_file)

    for param in parameters:
        try:
            out_parameters.update({param: general_info[param]})
        except KeyError:
            try:
                out_parameters.update({param: image_defs[param]})
            except KeyError:
                raise
    return out_parameters


def _process_gen_dict(gen_dict):
    # Process `gen_dict` key, values into `general_info`
    ####
    """
    adapten from https://github.com/nipy/nibabel/blob/master/nibabel/parrec.py
    to work with msec in par file

    """

    import numpy as np

    _hdr_key_dict = {
        'Protocol name': ('protocol_name',),
        'Technique': ('technique',),
        'Examination date/time': ('exam_date',),
        'Scan Duration [sec]': ('scan_duration', float),
        'Angulation midslice(ap,fh,rl)[degr]': ('angulation', float, (3,)),
        'Water Fat shift [pixels]': ('water_fat_shift', float),
        'EPI factor        <0,1=no EPI>': ('epi_factor', float),
        'Acquisition nr': ("acquisition_nr", int),
    }

    slice_orientation_translation = {1: 'transverse',
                                     2: 'sagittal',
                                     3: 'coronal',
                                     }
    rec_dir = {'transverse': 2,
               'sagittal': 0,
               'coronal': 1,
               }

    general_info = {}
    for key, value in gen_dict.items():
        # get props for this hdr field
        if key in _hdr_key_dict.keys():
            props = _hdr_key_dict[key]
            # turn values into meaningful dtype
            if len(props) == 2:
                # only dtype spec and no shape
                value = props[1](value)
            elif len(props) == 3:
                # array with dtype and shape
                value = np.fromstring(value, props[1], sep=' ')
                # if shape is None, allow arbitrary length
                if props[2] is not None:
                    value.shape = props[2]
            general_info[props[0]] = value
    return general_info


# higher level conversion
def deface_data(nii_file, nii_output_dir, out_filename):
    old_wd = os.getcwd()
    os.chdir(nii_output_dir)
    defaced_file = os.path.join(nii_output_dir, out_filename + "_defaced.nii.gz")
    cmd = f"pydeface {nii_file}"
    print(cmd)
    os.system(cmd)
    # replace file with face with defaced file
    os.remove(nii_file)
    os.rename(defaced_file, nii_file)
    os.chdir(old_wd)


# BVECS OPERATIONS
def dwi_treat_bvecs(abs_par_file, bids_file, bvecs_from_scanner_file, nii_output_dir, par_file):
    '''
    replaces dcm2niix bvecs with rotated, own bvecs
    adds angulation to json
    '''
    add_additional_bids_parameters_from_par(abs_par_file, bids_file, {"angulation": "Angulation"})
    # remove dcm2niix bvecs and replace with own, rotated LAS bvecs
    bvecs_file = glob(os.path.join(nii_output_dir, "*.bvec"))[0]
    os.remove(bvecs_file)
    bvecs_from_scanner = np.genfromtxt(bvecs_from_scanner_file)
    rotated_bvecs_ras = rotate_bvecs(bvecs_from_scanner, par_file)
    rotated_bvecs_las = rotated_bvecs_ras.copy()
    rotated_bvecs_las[0] *= -1
    np.savetxt(bvecs_file, rotated_bvecs_las.T, fmt="%.5f")
    add_info_to_json(bids_file, {"BvecsInfo": "rotated for angulation and in LAS space"})


# bvecs operations
def rotate_bvecs(bvecs_from_scanner, par_file):
    "takes bvecs from scanner, reads angulation from par_file and rotates bvecs"
    params = get_par_info(par_file, ["angulation", "slice orientation"])
    ap, fh, rl = params["angulation"]
    orient = params["slice orientation"][0]
    rotated_bvecs = rotate_vectors(bvecs_from_scanner, -ap, -fh, -rl, orient)
    return rotated_bvecs


def rotate_vectors(directions, ap, fh, rl, orient):
    """
    python implementation of matlab script rotDir

    function to rotate diffusion directions from a Philips *.par file
    returns rotated bvecs in RAS space; test with LHAB data
     input:
               directions : diffusion directions ( nx3 matrix ) [ap fh rl]
               ap         : angulation AP ( in degrees )
               fh         : angulation FH ( in degrees )
               rl         : angulation RL ( in degrees )
               orient     : orientation ( TRA==1 / SAG==2 / COR==3 )

     output:
               directions : rotatet diffusion directions ( nx3 matrix )


     BEWARE : Angulations are iverted versions of par file angulations
              the angulations are expected to be in degrees
    """
    pi, sin, cos = np.pi, np.sin, np.cos
    ap = ap * pi / 180.
    fh = fh * pi / 180.
    rl = rl * pi / 180.

    # % create rotation matrices
    rotap = np.array([[1, 0, 0],
                      [0, cos(ap), -sin(ap)],
                      [0, sin(ap), cos(ap)]])

    rotfh = np.array([[cos(fh), 0, sin(fh)],
                      [0, 1, 0],
                      [-sin(fh), 0, cos(fh)]])

    rotrl = np.array([[cos(rl), -sin(rl), 0],
                      [sin(rl), cos(rl), 0],
                      [0, 0, 1]])

    # do rotation in the patient's reference frame
    rot = np.dot(np.dot(rotfh, rotap), rotrl)
    tmp = directions.copy()
    for i in np.arange(np.size(directions, 0)):
        tmp[i, :] = (np.dot(rot, directions[i, :].T)).T
    directions = tmp.copy()

    # permutation (transform AP-FH-RL into X-Y-Z)
    tmp = directions.copy()
    directions[:, 0] = - tmp[:, 0]  # AP -> -X
    directions[:, 1] = tmp[:, 2]  # RL ->  Y
    directions[:, 2] = - tmp[:, 1]  # FH -> -Z

    # permutation (transform X-Y-Z into iX-iY-iZ)
    tmp = directions.copy()
    if 1 == orient:
        directions[:, 0] = tmp[:, 1]
        directions[:, 1] = - tmp[:, 0]
        directions[:, 2] = - tmp[:, 2]
    elif 2 == orient:
        directions[:, 0] = - tmp[:, 0]
        directions[:, 1] = tmp[:, 2]
        directions[:, 2] = - tmp[:, 1]
    elif 3 == orient:
        directions[:, 0] = tmp[:, 1]
        directions[:, 1] = tmp[:, 2]
        directions[:, 2] = - tmp[:, 0]

    # flip y
    directions[:, 1] *= -1

    return directions


def parse_acq_time(general_info):
    """
    Depending on the par file, date sometimes is represented as
    %Y.%m.%d / %H:%M:%S, sometimes as
    %d.%m.%Y / %H:%M:%S
    function returns acquisition time regardless of format
    """

    try:
        acq_time = pd.to_datetime(general_info["exam_date"], format="%Y.%m.%d / %H:%M:%S")
    except:
        try:
            acq_time = pd.to_datetime(general_info["exam_date"], format="%d.%m.%Y / %H:%M:%S")
        except:
            raise Exception("acuisition time in par file does neither conform to "
                            "%Y.%m.%d / %H:%M:%S, nor to %d.%m.%Y / %H:%M:%S. %s" % general_info)
    return acq_time


def parse_physio(input_file):
    """
    loads physio files
    removes acq date
    returns meta_data and physio_data (as df)
    """
    with open(input_file) as fi:
        data = fi.read().split("\n")
    _ = data.pop(1)  # remove acq date for anonymization

    meta_data = []
    physio_data = []
    for i, l in enumerate(data):
        if l.startswith("## "):
            meta_data.append(l)
        elif l.startswith("# "):
            header = l.strip("#").split(" ")
            header_line = i
    clean_header = list(filter(None, header))
    physio_data = pd.read_csv(input_file, header=header_line + 1, delim_whitespace=True, names=clean_header,
                              index_col=False)
    return meta_data, physio_data


def save_physio(output_filename_base, meta_data, physio_data):
    tsv_filename = output_filename_base + ".tsv.gz"
    json_filename = output_filename_base + ".json"

    header = physio_data.columns.tolist()
    json_data = {"Columns": header, "StartTime": 0, "SamplingFrequency": 496}
    add_info_to_json(json_filename, json_data, create_new=True)

    to_tsv(physio_data, tsv_filename, header=False)
