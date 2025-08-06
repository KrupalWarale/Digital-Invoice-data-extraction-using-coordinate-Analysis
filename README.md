# Digital-Invoice-data-extraction-using-coordinate-Analysis

This project provides a Python-based solution for extracting structured data from PDF documents, with a focus on accurately parsing tables and handling complex cell layouts. It leverages `pdfplumber` for PDF parsing and incorporates custom logic to restructure tables, especially those with multi-line content or merged cells.

## Features

-   **PDF Content Extraction**: Extracts both tables (cell-level data with bounding boxes) and individual words (with coordinates) from PDF pages.
-   **Intelligent Header Detection**: Identifies potential header rows in tables based on keyword matching.
-   **Robust Table Structuring**:
    -   Handles cells marked with `#$` (indicating multi-content or complex internal structure) by re-parsing their contained words and mapping them to appropriate columns.
    -   Dynamically reconstructs rows based on vertical word proximity, correctly separating multi-line content within logical cells.
    -   Aligns content from unmodified (non-`#$` marked) original PDFPlumber cells to the determined column boundaries.
-   **Maintains Original Order**: Ensures that the final structured table preserves the vertical order of rows as they appear in the PDF.
-   **Comprehensive Output**: Displays all detected structured tables within a PDF.

## How to Use

### Prerequisites

-   Python 3.x
-   pip (Python package installer)

### Installation

1.  **Clone the repository (if applicable) or download the project files.**
2.  **Install the required Python library**:
    ```bash
    pip install pdfplumber
    ```

### Running the Script

The main logic for PDF processing and structuring is located in `app.py`.

1.  **Place your PDF files** in the same directory as `app.py`.
2.  **Open `app.py`** and locate the `if __name__ == "__main__":` block at the bottom.
3.  **Set the `pdf_file_2` variable** to the name of your target PDF file (e.g., `"your_invoice.pdf"`).

    ```python
    if __name__ == "__main__":
        pdf_file_2 = "789.pdf" # Change this to your PDF filename
        coordinates_2 = extract_pdf_coordinates(pdf_file_2)
        print_formatted_output(coordinates_2, pdf_file_2)
    ```

4.  **Run the script** from your terminal:
    ```bash
    python app.py
    ```

The script will then print the extracted word coordinates, the "Final Marked Cells" view of the tables (showing how cells were marked for re-processing), and finally, the "All Structured Tables" output with resolved cells and correct row order.

## Project Structure

-   `app.py`: Contains the core logic for PDF coordinate extraction, table structuring, and formatted output.
-   `main.py`: A simpler example script using `pdfplumber` for basic table extraction (can be used for quick tests).
-   `*.pdf`: Sample PDF files used for testing.

## Dependencies

-   `pdfplumber`: For robust PDF parsing and extraction.
-   `re` (built-in): Used for regular expression operations within text analysis. 