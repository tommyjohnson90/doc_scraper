from flask import Flask, request, jsonify
from doc_scraper import scrape_site_and_supporting_docs, get_robot_parser, sanitize_filename, BASE_OUTPUT_DIR
import os
import datetime

app = Flask(__name__)

@app.route("/scrape_and_save", methods=["POST"])
def scrape_and_save():
    data = request.get_json()
    url = data.get("url")
    file_name = data.get("fileName")

    if not url or not file_name:
        return jsonify({"error": "Missing url or fileName"}), 400

    # Sanitize and timestamp folder name
    base_name = sanitize_filename(file_name)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = f"{base_name}_{timestamp}"
    output_dir = os.path.join(BASE_OUTPUT_DIR, output_folder)

    # Make sure directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Prepare and run the scrape
    rp = get_robot_parser(url)
    index_data, embedding_data = scrape_site_and_supporting_docs(url, output_dir, rp)

    # Calculate total file size
    total_size = sum(
        os.path.getsize(os.path.join(output_dir, f))
        for f in os.listdir(output_dir)
        if os.path.isfile(os.path.join(output_dir, f))
    )

    return jsonify({
        "fileName": output_folder,
        "fileSize": f"{total_size} bytes",
        "summary": f"Scraped content from {url} and saved {len(os.listdir(output_dir))} files."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
