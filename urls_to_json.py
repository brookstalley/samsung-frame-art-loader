import argparse
import json


def parse_arguments():
    parser = argparse.ArgumentParser(description="Process input and output file arguments.")
    parser.add_argument("input_file", type=str, help="The input file containing URLs")
    parser.add_argument(
        "output_file", type=str, nargs="?", default="DEFAULT", help="Output file (defaults to same as input but .json)"
    )

    args = parser.parse_args()
    return args


def read_urls_from_file(input_file):
    urls = []
    with open(input_file, "r") as file:
        for line in file:
            urls.append(line.strip())
    return urls


def write_urls_to_json(output_file, urls):
    data = {"schema_version": 1, "name": "placeholder", "default_resize": "cropped", "art": [{"url": url} for url in urls]}
    with open(output_file, "w") as file:
        json.dump(data, file, indent=4)


if __name__ == "__main__":
    args = parse_arguments()

    urls = read_urls_from_file(args.input_file)
    # If no output file is specified, default to the basename of the input file with a .json extension
    if args.output_file == "DEFAULT":
        input_filename = args.input_file.split(".")[0]  # Strip the file extension
        args.output_file = f"{input_filename}.json"

    write_urls_to_json(args.output_file, urls)

    print(f"URLs have been written to {args.output_file}")
