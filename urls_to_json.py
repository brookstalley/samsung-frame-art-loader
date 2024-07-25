import argparse
import json
import os


def parse_arguments():
    parser = argparse.ArgumentParser(description="Process input and output file arguments.")
    parser.add_argument("input_file", type=str, help="The input file containing URLs")
    parser.add_argument(
        "output_file", type=str, nargs="?", default="DEFAULT", help="Output file (defaults to same as input but .json)"
    )
    # --overwrite causes the whole file to be replaced
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file with the new URLs (default is to append to the existing",
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


def add_urls_to_json(output_file, urls):
    with open(output_file, "r") as file:
        data = json.load(file)

    existing_urls = [art["url"] for art in data["art"]]

    new_urls = [{"url": url} for url in urls if url not in existing_urls]
    data["art"].extend(new_urls)
    with open(output_file, "w") as file:
        json.dump(data, file, indent=4)


if __name__ == "__main__":
    args = parse_arguments()

    urls = read_urls_from_file(args.input_file)
    # If no output file is specified, default to the basename of the input file with a .json extension
    if args.output_file == "DEFAULT":
        input_filename = args.input_file.split(".")[0]  # Strip the file extension
        args.output_file = f"{input_filename}.json"

    if args.overwrite or not os.path.exists(args.output_file):
        write_urls_to_json(args.output_file, urls)
    else:
        add_urls_to_json(args.output_file, urls)

    print(f"URLs have been written to {args.output_file}")
