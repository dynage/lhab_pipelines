import argparse
from lhab_pipelines.nii_conversion.qc import move_excluded_scans

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('source_path', help='Directory containing sourcedata.'
                                            '\n original: bids_dir')
    parser.add_argument('exclusion_path', help='Directory where data will be moved '
                                               'should be stored.'
                                               '\n original: output_dir')
    parser.add_argument('analysis_level', help='Level of the analysis that will be performed. ',
                        choices=['group'])

    parser.add_argument('--exclusion_file', help="file with scans that should be excluded")
    parser.add_argument('--participant_label', help="Only works on these participants. If missing, 'sub-' is "
                                                    "prefixed.",
                        nargs="+")

    args = parser.parse_args()

    move_excluded_scans(args.source_path, args.exclusion_path, args.exclusion_file, args.participant_label)
