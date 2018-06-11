import os, re
from glob import glob
import pandas as pd

from lhab_pipelines.behav.behav_utils import export_behav_with_new_id

s_id_lut = "/Volumes/lhab_raw/01_RAW/00_PRIVATE_sub_lists/new_sub_id_lut.tsv"

in_dir = "/Volumes/lhab_public/03_Data/99_Cleaning/03_Health/00_textfiles/ready2use/"
out_dir = "/Volumes/lhab_public/03_Data/99_Cleaning/03_Health/00_textfiles/ready2use_newIDs/"

data_out_dir = os.path.join(out_dir, "data")
missing_out_dir = os.path.join(out_dir, "missing_info")

for p in [out_dir, data_out_dir, missing_out_dir]:
    if not os.path.exists(p):
        os.makedirs(p)

os.chdir(in_dir)



d = "health"

df_long = pd.DataFrame([], columns=["subject_id", "session_id", "conversion_date", "file"])
df_wide = pd.DataFrame([], columns=["subject_id", "session_id", "conversion_date"])
missing_info = pd.DataFrame([], columns=["subject_id", "session_id", "conversion_date", "file"])

os.chdir(in_dir)
xl_list = sorted(glob("*_data.xlsx"))
xl_list = [x for x in xl_list if "metadata" not in x]

for orig_file in xl_list:
    print(orig_file)
    data_file = os.path.join(in_dir, orig_file)
    p = re.compile(r"(lhab_)(\w*?)(_data)")
    test_name = p.findall(os.path.basename(orig_file))[0][1]

    metadata_str = "lhab_{}_metadata.xlsx".format(test_name) #"_".join(orig_file.split("_")[:2]) + "*" + " \
                                                                                               # ""_metadata.xlsx"
    g = glob(metadata_str)
    if len(g) > 1:
        raise Exception("More than one meta data file found: {}".format(g))
    elif len(g) == 0:
        raise Exception("No meta data file found: {}".format(metadata_str))
    else:
        metadata_file = g[0]
    data_file_path = os.path.join(in_dir, metadata_file)

    df_long_, df_wide_, missing_info_ = export_behav_with_new_id(data_file, data_file_path, s_id_lut)
    df_long_["file"] = orig_file
    missing_info_["file"] = metadata_file

    df_long = df_long.append(df_long_)
    df_wide = df_wide.merge(df_wide_, how="outer", on=["subject_id", "session_id", "conversion_date"])
    missing_info = missing_info.append(missing_info_)

# sort columns
c = df_long.columns.drop(["subject_id", "session_id", "file", "conversion_date"]).tolist()
df_long = df_long[["subject_id", "session_id"] + c + ["file", "conversion_date"]]
c = df_wide.columns.drop(["subject_id", "session_id", "conversion_date"]).tolist()
df_wide = df_wide[["subject_id", "session_id"] + c + ["conversion_date"]]
c = missing_info.columns.drop(["subject_id", "session_id", "file", "conversion_date"]).tolist()
missing_info = missing_info[["subject_id", "session_id"] + c + ["file", "conversion_date"]]

# sort rows
df_long.sort_values(["subject_id", "session_id"], inplace=True)
df_wide.sort_values(["subject_id", "session_id"], inplace=True)
missing_info.sort_values(["subject_id", "session_id"], inplace=True)

out_file = os.path.join(data_out_dir, d + "_long.tsv")
df_long.to_csv(out_file, index=None, sep="\t")

out_file = os.path.join(data_out_dir, d + "_wide.tsv")
df_wide.to_csv(out_file, index=None, sep="\t")

out_file = os.path.join(missing_out_dir, d + "_missing_info.tsv")
missing_info.to_csv(out_file, index=None, sep="\t")

