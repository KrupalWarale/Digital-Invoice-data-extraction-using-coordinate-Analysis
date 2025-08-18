import pdfplumber
import re

def is_table_end_row(row_text):
    """
    Checks if a row is a likely table-ending row based on keywords and numeric content.
    """
    # Keywords that often indicate the end of a table
    total_keywords = ['total', 'subtotal', 'grand total', 'invoice value','balance']
    row_lower = " ".join(row_text).lower()

    # Check for presence of end-of-table keywords
    if any(keyword in row_lower for keyword in total_keywords):
        # A table end row should also contain a number to be valid
        if re.search(r'\d', row_lower):
            return True
    return False

def extract_pdf_coordinates(pdf_path):
    """
    Extracts coordinates of all table cells (with text) and all words/expressions/phrases
    from a PDF using pdfplumber.
    """
    all_coordinates = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_data = {"tables": [], "words": []}
                # Extract structured tables
                for table in page.find_tables():
                    table_rows_data = []
                    # Extract raw text from the table
                    table_text_data = table.extract()
                    for row_idx, row in enumerate(table.rows):
                        current_row_cells = []
                        for col_idx, cell_bbox in enumerate(row.cells):
                            cell_text = None
                            if table_text_data and row_idx < len(table_text_data) and col_idx < len(table_text_data[row_idx]):
                                cell_text = table_text_data[row_idx][col_idx]
                            
                            if cell_bbox:
                                current_row_cells.append((cell_bbox, cell_text if cell_text else ""))
                            else:
                                current_row_cells.append((None, None))
                        table_rows_data.append(current_row_cells)
                    page_data["tables"].append(table_rows_data)

                # Extract all individual words from the page with their coordinates
                for word in page.extract_words():
                    page_data["words"].append((word['text'], word['x0'], word['top'], word['x1'], word['bottom']))
                
                all_coordinates[f"page_{page_num + 1}"] = page_data
    except FileNotFoundError:
        print(f"Error: The file at {pdf_path} was not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    return all_coordinates

def find_column_for_word(word_x0, word_x1, column_boundaries):
    """
    Find which column a word belongs to based on horizontal alignment.
    """
    word_center = (word_x0 + word_x1) / 2
    for col_idx, (col_x0, col_x1) in enumerate(column_boundaries):
        if word_center >= col_x0 and word_center <= col_x1:
            return col_idx
    return -1

def separate_rows_by_vertical_gap(cell_words):
    """
    Separates words into different rows based on vertical gaps between them.
    This is useful for multi-line content within a single cell.
    """
    if not cell_words:
        return []
    # Sort words primarily by their vertical position (top) and then horizontal position (x0)
    sorted_words = sorted(cell_words, key=lambda w: (w[2], w[1]))
    rows = []
    current_row = [sorted_words[0]]
    if len(sorted_words) > 1:
        # Calculate an average word height to use as a threshold
        avg_word_height = sum(w[4] - w[2] for w in sorted_words) / len(sorted_words)
        gap_threshold = avg_word_height * 0.7
        for i in range(1, len(sorted_words)):
            vertical_gap = sorted_words[i][2] - sorted_words[i-1][4]
            if vertical_gap > gap_threshold:
                rows.append(current_row)
                current_row = [sorted_words[i]]
            else:
                current_row.append(sorted_words[i])
    rows.append(current_row)
    return rows

def create_structured_table(table_rows, header_row_index, page_words):
    """
    Create a structured table that resolves cells marked with '#$' by re-parsing
    the words from the page based on their coordinates, and handles normal cells.
    """
    if header_row_index == -1 or header_row_index >= len(table_rows):
        return []

    header_cells = table_rows[header_row_index]
    column_boundaries = []
    for cell_bbox, _ in header_cells:
        if cell_bbox:
            column_boundaries.append((cell_bbox[0], cell_bbox[2]))

    if not column_boundaries:
        return []

    rows_with_positions = []
    
    # Process the header row separately
    header_row_text = [cell_data[1] if cell_data[1] is not None else "" for cell_data in header_cells]
    if header_cells and header_cells[0][0]:
        rows_with_positions.append((header_cells[0][0][1], header_row_text))

    for original_row_idx in range(header_row_index + 1, len(table_rows)):
        original_row_cells = table_rows[original_row_idx]
        is_marked_row = any(cell_data[1] and cell_data[1].startswith("#$") for cell_data in original_row_cells)

        if not is_marked_row:
            structured_row = [cell_data[1] if cell_data[1] is not None else "" for cell_data in original_row_cells]
            if original_row_cells and original_row_cells[0][0]:
                row_min_y = original_row_cells[0][0][1]
                rows_with_positions.append((row_min_y, structured_row))
        else:
            row_min_y = float('inf')
            row_max_y = 0
            for cell_bbox, _ in original_row_cells:
                if cell_bbox:
                    row_min_y = min(row_min_y, cell_bbox[1])
                    row_max_y = max(row_max_y, cell_bbox[3])
            
            # Find all words that fall within the vertical bounds of the current marked row
            words_in_row_area = [
                word_data for word_data in page_words 
                if word_data[2] >= row_min_y - 2 and word_data[4] <= row_max_y + 2
            ]
            logical_sub_rows = separate_rows_by_vertical_gap(words_in_row_area)
            
            for sub_row_words in logical_sub_rows:
                structured_row = [""] * len(column_boundaries)
                for word_text, word_x0, word_y0, word_x1, word_y1 in sub_row_words:
                    col_idx = find_column_for_word(word_x0, word_x1, column_boundaries)
                    if col_idx != -1:
                        current_cell_content = structured_row[col_idx]
                        if current_cell_content:
                            structured_row[col_idx] = f"{current_cell_content} {word_text}"
                        else:
                            structured_row[col_idx] = word_text
                
                if sub_row_words:
                    rows_with_positions.append((sub_row_words[0][2], structured_row))

    rows_with_positions.sort(key=lambda x: x[0])
    final_structured_table = [row_data for _, row_data in rows_with_positions]
    return final_structured_table

def print_formatted_output(coordinates_data, pdf_filename):
    COLUMN_KEYWORDS = [
        "item", "description", "product", "name", "particulars",
        "qty", "quantity", "rate", "price", "amount", "total",
        "gst", "tax", "hsn", "code", "unit", "net", "discount",
        "cgst", "sgst", "utgst", "igst", "cess"
    ]

    print(f"--- PDFPlumber Table & Word Extraction for '{pdf_filename}' ---")

    for page_name, page_data in coordinates_data.items():
        print(f"\n--- {page_name.replace('_', ' ').capitalize()} ---")
        print(f"Number of tables found: {len(page_data['tables'])}")

        for table_idx, table_rows in enumerate(page_data['tables']):
            header_found = False
            header_row_index = -1
            is_marking_active = False  # New flag to control marking

            # First pass: Identify the true header row
            for row_idx, row_cells in enumerate(table_rows):
                row_text_content = [cell[1].lower() for cell in row_cells if cell[1]]
                row_contains_metadata = bool(re.search(r':\s*\S', " ".join(row_text_content)))
                matched_keyword_count = sum(1 for keyword in COLUMN_KEYWORDS if any(keyword in cell_text for cell_text in row_text_content))

                is_header = matched_keyword_count >= 3 and not row_contains_metadata
                if is_header and not header_found:
                    header_found = True
                    header_row_index = row_idx
                    is_marking_active = True  # Start marking from the header row

            # Second pass: Mark problematic cells with '#$'
            if header_found:
                header_cells = table_rows[header_row_index]
                column_boundaries = []
                for cell_bbox, _ in header_cells:
                    if cell_bbox:
                        column_boundaries.append((cell_bbox[0], cell_bbox[2]))

                if column_boundaries:
                    for row_idx in range(header_row_index, len(table_rows)):
                        if not is_marking_active:
                            # Skip if we are no longer in a table
                            continue
                            
                        for col_idx, cell_data in enumerate(table_rows[row_idx]):
                            cell_bbox, cell_text = cell_data
                            
                            if cell_text:
                                # Logic 1: Check for multiple newlines
                                if cell_text.count('\n') > 3:
                                    table_rows[row_idx][col_idx] = (cell_bbox, f"#$ {cell_text}")
                                    continue
                                
                                # Logic 2: Check if word bounding boxes span multiple columns
                                words_in_cell = [word for word in page_data['words'] if cell_bbox and word[2] >= cell_bbox[1] and word[4] <= cell_bbox[3] and word[1] >= cell_bbox[0] and word[3] <= cell_bbox[2]]
                                
                                if words_in_cell:
                                    min_x0 = min(word[1] for word in words_in_cell)
                                    max_x1 = max(word[3] for word in words_in_cell)
                                    
                                    start_col = find_column_for_word(min_x0, min_x0, column_boundaries)
                                    end_col = find_column_for_word(max_x1, max_x1, column_boundaries)
                                    
                                    if start_col != end_col:
                                        table_rows[row_idx][col_idx] = (cell_bbox, f"#$ {cell_text}")

                        # Check if this row is a table-ending row and stop marking if it is
                        row_text_for_end_check = [cell_data[1] for cell_data in table_rows[row_idx] if cell_data[1]]
                        if is_table_end_row(row_text_for_end_check):
                            is_marking_active = False

            structured_table = []
            if header_found:
                structured_table = create_structured_table(table_rows, header_row_index, page_data['words'])

            print(f"\n--- Structured Table {table_idx + 1} ---")
            
            table_in_progress = False
            
            for row_idx, row in enumerate(table_rows):
                if row_idx == header_row_index:
                    break
                if any(cell[1] for cell in row):
                    print([cell[1] for cell in row if cell[1]])

            if not structured_table:
                for row in table_rows:
                    if any(cell[1] for cell in row):
                        print([cell[1] for cell in row if cell[1]])
                continue

            for row_idx, row in enumerate(structured_table):
                if row_idx == 0:
                    print("__table start__")
                    table_in_progress = True
                
                print(row)

                is_end_row = is_table_end_row([str(cell) for cell in row if cell])
                
                if is_end_row and table_in_progress:
                    is_next_row_a_header = False
                    if row_idx + 1 < len(structured_table):
                        next_row_text = " ".join([str(cell).lower() for cell in structured_table[row_idx + 1] if cell])
                        matched_keyword_count_next = sum(1 for keyword in COLUMN_KEYWORDS if keyword in next_row_text)
                        if matched_keyword_count_next >= 3 and "in words" not in next_row_text:
                            is_next_row_a_header = True

                    if not is_next_row_a_header:
                        print("__table end__")
                        table_in_progress = False
            
            if table_in_progress:
                print("__table end__")
                
if __name__ == "__main__":
    pdf_file_2 = "123.pdf"
    coordinates_2 = extract_pdf_coordinates(pdf_file_2)
    
    if coordinates_2:
        print_formatted_output(coordinates_2, pdf_file_2)
