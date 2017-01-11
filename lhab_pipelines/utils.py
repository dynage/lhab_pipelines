import json
import os
import warnings

# docker stuff
import pandas as pd
from bids.grabbids import BIDSLayout
import zipfile
from io import StringIO
from collections import OrderedDict
import numpy


def get_docker_container_name():
    docker_container_name = os.getenv("DOCKER_IMAGE")
    return docker_container_name


def check_docker_container_version(requested_v):
    actual_v = get_docker_container_name()
    if actual_v:
        if not actual_v == requested_v:
            raise RuntimeError("Requested docker version: %s, but running %s" % (requested_v, actual_v))
        else:
            print("Running docker: %s" % actual_v)
    else:
        warnings.warn("Not running in Docker env!")


def to_tsv(df, filename, header=True):
    df.to_csv(filename, sep="\t", index=False, header=header)


def read_tsv(filename):
    return pd.read_csv(filename, sep="\t")


def get_json(bids_file):
    with open(bids_file) as fi:
        bids_data = json.load(fi)
    return bids_data


def add_info_to_json(bids_file, new_info, create_new=False):
    # if create_new=True: if file does not exist, file is created and new_info is written out
    if os.path.exists(bids_file):
        bids_data = get_json(bids_file)
    elif (not os.path.exists(bids_file)) and create_new:
        bids_data = {}
    else:
        raise FileNotFoundError("%s does not exist. Something migth be wrong. If a file should create, "
                                "use create_new=True " % bids_file)

    for k, v in new_info.items():
        if isinstance(v, numpy.ndarray):
            new_info[k] = v.tolist()
    bids_data.update(new_info)

    with open(bids_file, "w") as fi:
        json.dump(OrderedDict(sorted(bids_data.items())), fi, indent=4)


def reduce_sub_files(bids_dir, output_file, sub_file):
    df = pd.DataFrame([])
    layout = BIDSLayout(bids_dir)
    files = layout.get(extensions=sub_file)
    for file in [f.filename for f in files]:
        print(file)
        df_ = read_tsv(file)
        df = pd.concat((df, df_))

    to_tsv(df, os.path.join(bids_dir, output_file))


def read_protected_file(zfile, pwd, datafile):
    """
    opens encrypted zipfile and reads table sep. datafile (txt)
    returns a data frame
    """
    pwd = bytes(pwd, 'utf-8')
    fi = zipfile.ZipFile(zfile)
    data = fi.read(datafile, pwd=pwd)
    data = data.decode()
    fi.close()
    df = pd.read_csv(StringIO(data), sep="\t")
    df.set_index("subject_id", inplace=True)
    return df
