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
        pdf_file_2 = "invoice.pdf" # Change this to your PDF filename
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

## Problem Solving Approach

Our approach to solving the complex problem of accurate data extraction from digital invoices involved an iterative process focused on identifying and addressing specific challenges presented by PDF structures:

1.  **Initial PDFPlumber Extraction**: We started by leveraging `pdfplumber` to get raw table data and individual word coordinates. This provided a foundational understanding of how data is physically laid out.

2.  **Identifying "Loopholes" in Table Structures**: We observed that `pdfplumber`'s default table extraction often presented "loopholes" or inaccuracies, especially with:
    -   **Multi-line content within a single logical cell**: Text spanning multiple lines within what should be a single table cell.
    -   **Merged cells or complex layouts**: Where `pdfplumber` might split a logical cell into multiple physical cells, or vice-versa, resulting in `None` values or misaligned data.
    -   **Inconsistent Row Ordering**: The order of extracted rows did not always match the visual or logical order.

3.  **Introducing `#$` Marking for Problematic Cells**: To explicitly flag and address multi-content cells, we introduced a `#$` marking mechanism. This allowed us to identify cells that required special re-processing.

4.  **Refining Table Structuring Logic (`create_structured_table`)**:
    -   **Dynamic Column Boundary Detection**: We developed robust logic to accurately determine column boundaries based on header cell positions.
    -   **Word-to-Column Mapping**: Instead of relying solely on `pdfplumber`'s cell boundaries for problematic areas, we shifted to mapping individual words directly to the determined columns based on their `x` (horizontal) coordinates and overlap with column boundaries. This is crucial for handling fragmented or misaligned text.
    -   **Vertical Row Separation (`separate_rows_by_vertical_gap`)**: We implemented a mechanism to dynamically group words into logical rows based on significant vertical gaps between them. This inherently resolves multi-line content within a logical cell.
    -   **Combined Processing of Marked and Unmarked Rows**: The `create_structured_table` function was enhanced to process both `#$` marked rows (applying the detailed word-level restructuring) and unmarked rows (aligning their original content to columns).

5.  **Ensuring Consistent Vertical Order**: A key challenge was maintaining the correct vertical order of rows in the final structured table, especially when combining restructured sub-rows and direct transfers. We standardized the calculation of each structured row's vertical position (`y_pos`) by consistently using the minimum `y0` coordinate of the words comprising that row. This `y_pos` then serves as a reliable key for sorting all rows, ensuring the output matches the visual order of the invoice.

6.  **Iterative Refinement and Testing**: The approach involved continuous testing with various invoice layouts (e.g., `123.pdf`, `abc.pdf`, `789.pdf`). Each test revealed new edge cases or inconsistencies, leading to further refinements in the logic, particularly in the heuristics for word grouping and column assignment. This iterative cycle of identifying issues and implementing targeted solutions has led to the current robust extraction capabilities. 
