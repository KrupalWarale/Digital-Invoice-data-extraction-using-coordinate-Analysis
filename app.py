import pdfplumber
import re

def extract_pdf_coordinates(pdf_path):
    """
    Extracts coordinates of all table cells (with text) and all words/expressions/phrases
    from a PDF using pdfplumber.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        dict: A dictionary where keys are page numbers and values contain lists of coordinates
              for tables (cell-level with text) and words.
    """
    all_coordinates = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_data = {"tables": [], "words": []}

            # Extract table cell coordinates and text
            for table in page.find_tables():
                table_rows_data = []
                table_text_data = table.extract() # Extracts text as list of lists

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

            # Extract word/phrase coordinates (including text)
            for word in page.extract_words():
                page_data["words"].append((word['text'], word['x0'], word['top'], word['x1'], word['bottom']))
            
            all_coordinates[f"page_{page_num + 1}"] = page_data
    
    return all_coordinates

def find_column_for_word(word_x0, word_x1, column_boundaries):
    """
    Find which column a word belongs to based on horizontal alignment with defined column boundaries.
    Args:
        word_x0, word_x1: Horizontal coordinates of the word
        column_boundaries: List of (x0, x1) tuples for each column
    Returns:
        int: Column index if found, -1 if not found. Returns the first column that the word largely overlaps with.
    """
    word_center = (word_x0 + word_x1) / 2
    
    for col_idx, (col_x0, col_x1) in enumerate(column_boundaries):
        # Check if the word's center is within the column, or if it largely overlaps
        # A more robust overlap check might be needed for complex cases
        overlap_start = max(word_x0, col_x0)
        overlap_end = min(word_x1, col_x1)
        
        # Calculate overlap percentage. If a word significantly overlaps a column, assign it.
        # This heuristic can be adjusted.
        if overlap_end > overlap_start:
            overlap_width = overlap_end - overlap_start
            word_width = word_x1 - word_x0
            col_width = col_x1 - col_x0

            if word_width > 0 and (overlap_width / word_width > 0.5 or overlap_width / col_width > 0.5):
                return col_idx
            elif word_x0 >= col_x0 and word_x1 <= col_x1: # Word fully contained
                return col_idx
            elif word_center >= col_x0 and word_center <= col_x1: # Word center in column
                return col_idx
            
    return -1

def separate_rows_by_vertical_gap(cell_words):
    """
    Separate words into different rows based on vertical gaps between them.
    This function is now more general, operating on any list of words.
    Args:
        cell_words: List of word data tuples (text, x0, y0, x1, y1)
    Returns:
        list: List of row groups, each containing words for that row, sorted horizontally
    """
    if not cell_words:
        return []
    
    # Sort words primarily by vertical position (y0), then by horizontal (x0)
    sorted_words = sorted(cell_words, key=lambda w: (w[2], w[1]))  # Sort by y0, then x0
    
    rows = []
    current_row = [sorted_words[0]]
    
    # Calculate average word height for gap threshold based on the first few words
    # to avoid skewed averages from very short/tall words.
    sample_words = sorted_words[:min(len(sorted_words), 10)]
    word_heights = [word[4] - word[2] for word in sample_words if word[4] - word[2] > 0]
    avg_word_height = sum(word_heights) / len(word_heights) if word_heights else 10
    
    # Gap threshold: a gap larger than this suggests a new row
    gap_threshold = avg_word_height * 0.7  # Adjusted heuristic, can be fine-tuned
    
    # Track current row's max bottom (y1) for gap calculation
    current_row_max_y1 = sorted_words[0][4]
    
    for i in range(1, len(sorted_words)):
        word_text, word_x0, word_y0, word_x1, word_y1 = sorted_words[i]
        
        # Calculate vertical gap from the bottom of the current row to the top of the next word
        vertical_gap = word_y0 - current_row_max_y1
        
        # If the gap is significant, start a new row
        if vertical_gap > gap_threshold:
            # Sort words in the current_row by x0 before appending
            rows.append(sorted(current_row, key=lambda w: w[1]))
            current_row = [sorted_words[i]]
            current_row_max_y1 = word_y1 # Reset max y1 for the new row
        else:
            # Word belongs to the current row
            current_row.append(sorted_words[i])
            current_row_max_y1 = max(current_row_max_y1, word_y1) # Update max y1
    
    # Add the last row
    if current_row:
        rows.append(sorted(current_row, key=lambda w: w[1])) # Sort last row as well
    
    return rows

def create_structured_table(table_rows, header_row_index, page_words):
    """
    Create a structured table that combines both re-parsed (for #$ marked cells)
    and directly transferred (for unmarked cells) content, maintaining vertical order.
    Args:
        table_rows: Raw table data from PDFPlumber (list of rows, each row is list of (bbox, text))
        header_row_index: Index of the header row
        page_words: List of all words on the page with coordinates (text, x0, y0, x1, y1)
    Returns:
        list: Structured table data (list of lists, where inner list is a row of strings)
    """
    if header_row_index == -1 or header_row_index >= len(table_rows):
        return []

    header_cells = table_rows[header_row_index]

    # 1. Determine robust column boundaries from header cells
    column_boundaries = []
    for cell_bbox, cell_text in header_cells:
        if cell_bbox:
            column_boundaries.append((cell_bbox[0], cell_bbox[2])) # (x0, x1)

    if not column_boundaries:
        return []

    # List to store (vertical_position, structured_row_data) tuples for sorting
    rows_with_positions = []

    # Iterate through all original pdfplumber rows
    for original_row_idx, original_row_cells in enumerate(table_rows):
        current_row_has_marked_cells = False
        for cell_bbox, cell_text in original_row_cells:
            if cell_text and cell_text.startswith("#$"):
                current_row_has_marked_cells = True
                break

        if current_row_has_marked_cells:
            # This row (or set of original pdfplumber cells) contains #$ marked content.
            # We need to extract words that belong to this original row's vertical span
            # and then re-structure them.

            row_min_y = float('inf')
            row_max_y = float('-inf')
            for cell_bbox, _ in original_row_cells:
                if cell_bbox:
                    row_min_y = min(row_min_y, cell_bbox[1])
                    row_max_y = max(row_max_y, cell_bbox[3])

            if row_min_y == float('inf'): # No valid bbox for this original row
                continue # Skip this row (or handle as empty/error)

            words_in_this_original_row = []
            tolerance_y = 2 # Small vertical tolerance for word inclusion
            for word_data in page_words:
                word_text, word_x0, word_y0, word_x1, word_y1 = word_data
                # Check if word vertically overlaps with the original row's vertical range
                if (word_y0 >= row_min_y - tolerance_y and word_y0 <= row_max_y + tolerance_y) or \
                   (word_y1 >= row_min_y - tolerance_y and word_y1 <= row_max_y + tolerance_y) or \
                   (word_y0 <= row_min_y - tolerance_y and word_y1 >= row_max_y + tolerance_y):
                    words_in_this_original_row.append(word_data)

            # Separate words into logical sub-rows based on vertical gaps
            logical_sub_rows = separate_rows_by_vertical_gap(words_in_this_original_row)

            # Map words in each logical sub-row to columns and add to final list
            for sub_row_words in logical_sub_rows:
                structured_sub_row = [""] * len(column_boundaries)
                words_in_cols = {i: [] for i in range(len(column_boundaries))}
                
                # Get y_position for this sub_row (using the y0 of the first word)
                # Use the y0 of the first word in the already vertically sorted sub_row_words
                sub_row_y_pos = sub_row_words[0][2] if sub_row_words else row_min_y # Fallback if no words

                for word_text, word_x0, word_y0, word_x1, word_y1 in sub_row_words:
                    col_idx = find_column_for_word(word_x0, word_x1, column_boundaries)
                    if col_idx != -1:
                        words_in_cols[col_idx].append(word_text)
                    else:
                        # Fallback: find closest column if not directly within one
                        min_dist = float('inf')
                        closest_col_idx = -1
                        word_center = (word_x0 + word_x1) / 2
                        for i, (col_x0, col_x1) in enumerate(column_boundaries):
                            col_center = (col_x0 + col_x1) / 2
                            dist = abs(word_center - col_center)
                            if dist < min_dist:
                                min_dist = dist
                                closest_col_idx = i
                        if closest_col_idx != -1:
                            words_in_cols[closest_col_idx].append(word_text)

                for col_idx, words in words_in_cols.items():
                    if words:
                        structured_sub_row[col_idx] = " ".join(words)

                if any(cell.strip() for cell in structured_sub_row):
                    # Collect all words that contributed to this structured_sub_row
                    # to get an accurate y_pos for sorting
                    words_for_sub_row_y_pos = []
                    for word_data in sub_row_words:
                        if word_data[0] in " ".join(structured_sub_row): # Simple check if word text is in the final cell string
                            words_for_sub_row_y_pos.append(word_data)

                    # Use the minimum y0 of all words in this sub_row as its vertical position
                    sub_row_y_pos = min(word[2] for word in words_for_sub_row_y_pos) if words_for_sub_row_y_pos else row_min_y

                    rows_with_positions.append((sub_row_y_pos, structured_sub_row))

        else:
            # This row does NOT contain #$ marks, so just transfer its content and align to columns.
            
            # First, find all page words that fall within this original row's vertical range
            raw_row_min_y = float('inf')
            raw_row_max_y = float('-inf')
            for cell_bbox, _ in original_row_cells:
                if cell_bbox:
                    raw_row_min_y = min(raw_row_min_y, cell_bbox[1])
                    raw_row_max_y = max(raw_row_max_y, cell_bbox[3])

            words_in_raw_row = []
            if raw_row_min_y != float('inf'): # Only collect words if row has valid bbox
                tolerance_y = 2
                for word_data in page_words:
                    word_text, word_x0, word_y0, word_x1, word_y1 = word_data
                    if (word_y0 >= raw_row_min_y - tolerance_y and word_y0 <= raw_row_max_y + tolerance_y) or \
                       (word_y1 >= raw_row_min_y - tolerance_y and word_y1 <= raw_row_max_y + tolerance_y) or \
                       (word_y0 <= raw_row_min_y - tolerance_y and word_y1 >= raw_row_max_y + tolerance_y):
                        words_in_raw_row.append(word_data)
            
            # Calculate raw_row_y_pos based on words, for consistent sorting
            raw_row_y_pos = min(word[2] for word in words_in_raw_row) if words_in_raw_row else original_row_idx * 100 # Fallback
            
            mapped_raw_row = [""] * len(column_boundaries)
            for cell_idx, (cell_bbox, cell_text) in enumerate(original_row_cells):
                if cell_text is not None: # Only process if there's text (even if empty string)
                    if cell_bbox:
                        assigned_col = -1 
                        
                        # 1. Try to assign based on best horizontal overlap
                        best_col_idx = -1
                        max_overlap_width = 0
                        cell_x0, cell_y0, cell_x1, cell_y1 = cell_bbox

                        for col_b_idx, (col_x0, col_x1) in enumerate(column_boundaries):
                            # Calculate horizontal overlap
                            overlap_x_start = max(cell_x0, col_x0)
                            overlap_x_end = min(cell_x1, col_x1)
                            
                            if overlap_x_end > overlap_x_start:
                                overlap_width = overlap_x_end - overlap_x_start
                                if overlap_width > max_overlap_width:
                                    max_overlap_width = overlap_width
                                    best_col_idx = col_b_idx
                        
                        if best_col_idx != -1:
                            assigned_col = best_col_idx
                        else:
                            # 2. Fallback: if no clear overlap, try closest column by center
                            min_dist_to_col_center = float('inf')
                            closest_col_idx = -1
                            cell_center_x = (cell_x0 + cell_x1) / 2
                            for col_b_idx, (col_x0, col_x1) in enumerate(column_boundaries):
                                col_center_x = (col_x0 + col_x1) / 2
                                dist = abs(cell_center_x - col_center_x)
                                if dist < min_dist_to_col_center:
                                    min_dist_to_col_center = dist
                                    closest_col_idx = col_b_idx
                            if closest_col_idx != -1:
                                assigned_col = closest_col_idx
                        
                        if assigned_col != -1:
                            if mapped_raw_row[assigned_col]:
                                mapped_raw_row[assigned_col] += " " + cell_text
                            else:
                                mapped_raw_row[assigned_col] = cell_text
                        elif len(column_boundaries) > 0: # Final fallback if nothing else works, put in first column
                            if mapped_raw_row[0]:
                                mapped_raw_row[0] += " " + cell_text
                            else:
                                mapped_raw_row[0] = cell_text
                    else:
                        # If no bbox, but text exists, append to first column as a fallback.
                        if len(column_boundaries) > 0:
                            if mapped_raw_row[0]:
                                mapped_raw_row[0] += " " + cell_text
                            else:
                                mapped_raw_row[0] = cell_text
            
            if any(cell.strip() for cell in mapped_raw_row):
                rows_with_positions.append((raw_row_y_pos, mapped_raw_row))
    
    # Sort all rows (both restructured and raw) by their vertical position to ensure correct sequence
    rows_with_positions.sort(key=lambda x: x[0])

    final_structured_table = []
    for y_pos, row_data in rows_with_positions:
        final_structured_table.append(row_data)
    
    return final_structured_table

def print_formatted_output(coordinates_data, pdf_filename):
    COLUMN_KEYWORDS = [
        "item", "description", "product", "name", "particulars",
        "qty", "quantity", "rate", "price", "amount", "total",
        "gst", "tax", "hsn", "code", "unit", "net", "discount"
    ]

    all_structured_tables = []

    print(f"--- PDFPlumber Table & Word Extraction for '{pdf_filename}' ---")

    for page_name, page_data in coordinates_data.items():
        print(f"\n--- {page_name.replace('_', ' ').capitalize()} ---")

        # Print Table Data
        print(f"Number of tables found: {len(page_data['tables'])}")
        for table_idx, table_rows in enumerate(page_data['tables']):
            print(f"Table {table_idx + 1}:")
            header_found_in_table = False
            header_row_index = -1 # Store the index of the header row

            for row_idx, row_cells in enumerate(table_rows):
                formatted_cells_display = [] # For printing original cells
                row_text_content = []
                none_count_in_row = 0 # Count None cells in the current row

                for cell_data in row_cells:
                    cell_bbox = cell_data[0]
                    cell_text = cell_data[1]
                    if cell_bbox:
                        formatted_cells_display.append(f"('{cell_bbox[0]:.2f}, {cell_bbox[1]:.2f}'), ('{cell_bbox[2]:.2f}, {cell_bbox[3]:.2f}')")
                    else:
                        formatted_cells_display.append(str(None))
                        none_count_in_row += 1

                    if cell_text:
                        row_text_content.append(cell_text.lower())
                
                # Print the original row content
                print(f"    Row {row_idx} (Original): {formatted_cells_display}")

                # Check for header keywords in the row and word count
                row_is_header = False
                matched_keyword_count = 0
                row_contains_metadata_pattern = False # New flag to detect metadata patterns

                for cell_text_in_row_content in row_text_content:
                    if cell_text_in_row_content and cell_text_in_row_content.strip() != '':
                        # Check for metadata pattern (e.g., 'key: value')
                        if re.search(r':\s*\S', cell_text_in_row_content):
                            row_contains_metadata_pattern = True
                            # If a metadata pattern is found, no need to check other cells for metadata in this row
                            # and this row should not be a header, so we can stop further checks for header keywords.
                            # However, for debugging, let's allow keyword count to complete, just mark the flag.

                        for keyword in COLUMN_KEYWORDS:
                            if keyword in cell_text_in_row_content:
                                matched_keyword_count += 1
                
                print(f"    Debug: Row {row_idx}, Text Content: {row_text_content}, Matched Keywords: {matched_keyword_count}, Contains Metadata: {row_contains_metadata_pattern}")

                if matched_keyword_count >= 3 and not row_contains_metadata_pattern: # Modified condition
                    row_is_header = True
                    header_found_in_table = True
                    header_row_index = row_idx
                
                if row_is_header:
                    print(f"    --> Possible header row detected at Row {row_idx}")

                # New logic to mark cells
                if header_found_in_table and row_idx > header_row_index and none_count_in_row > 1:
                    for i, cell_data in enumerate(row_cells):
                        cell_text = cell_data[1]
                        cell_bbox = cell_data[0] # Get cell bounding box for new logic

                        # Existing logic for marking cells based on content and newlines
                        should_mark_based_on_content_and_newlines = False
                        if cell_text and cell_text.count('\n') > 3:
                            contains_digit = bool(re.search(r'\d', cell_text))
                            contains_letter = bool(re.search(r'[a-zA-Z]', cell_text))
                            contains_symbol = bool(re.search(r'[^\w\s]', cell_text))
                            contains_multiple_phrases = len(cell_text.split()) > 1

                            if contains_digit and contains_letter and contains_symbol and contains_multiple_phrases:
                                should_mark_based_on_content_and_newlines = True

                        # New logic to mark cells based on significant horizontal gaps between words
                        should_mark_based_on_horizontal_gap = False
                        if cell_text and cell_bbox: # Only proceed if there's text and a bounding box
                            current_cell_words = []
                            # Find words that fall within this cell's bounding box
                            cell_x0, cell_y0, cell_x1, cell_y1 = cell_bbox
                            for word_data in page_data['words']:
                                word_text, word_x0, word_y0, word_x1, word_y1 = word_data
                                # Check if word is within the current cell's bounding box (with a bit of tolerance)
                                if (word_x0 >= cell_x0 - 2 and word_x1 <= cell_x1 + 2 and
                                    word_y0 >= cell_y0 - 2 and word_y1 <= cell_y1 + 2):
                                    current_cell_words.append((word_text, word_x0, word_y0, word_x1, word_y1))

                            if len(current_cell_words) > 1:
                                current_cell_words.sort(key=lambda w: w[1]) # Sort by x0 for horizontal gap analysis
                                # Calculate average word width for this cell to determine relative gap
                                word_widths = [w[3] - w[1] for w in current_cell_words] # x1 - x0
                                avg_word_width = sum(word_widths) / len(word_widths) if word_widths else 10 # Fallback
                                horizontal_gap_threshold = avg_word_width * 1.5 # Heuristic: 150% of average word width

                                # Check for significant gaps between consecutive words
                                for k in range(len(current_cell_words) - 1):
                                    gap = current_cell_words[k+1][1] - current_cell_words[k][3] # x0 of next word - x1 of current word
                                    if gap > horizontal_gap_threshold:
                                        should_mark_based_on_horizontal_gap = True
                                        break

                        # New logic: Check if the sum of all gaps is greater than the average word width
                        should_mark_based_on_sum_of_gaps = False
                        if len(current_cell_words) > 1:
                            total_gap_in_cell = 0
                            for k in range(len(current_cell_words) - 1):
                                gap = current_cell_words[k+1][1] - current_cell_words[k][3]
                                total_gap_in_cell += gap
                            if total_gap_in_cell > avg_word_width:
                                should_mark_based_on_sum_of_gaps = True

                        # Apply marking if any of the conditions are met
                        if (should_mark_based_on_content_and_newlines or should_mark_based_on_horizontal_gap or should_mark_based_on_sum_of_gaps) and cell_text and cell_text.strip() != '':
                            original_cell_text = table_rows[row_idx][i][1]
                            table_rows[row_idx][i] = (table_rows[row_idx][i][0], f"#$ {original_cell_text}")

                # Prepare formatted_cells for printing after potential modification
                formatted_cells_after_marking = []
                for cell_data in row_cells:
                    cell_bbox = cell_data[0]
                    cell_text = cell_data[1] # Get updated cell_text
                    if cell_bbox:
                        formatted_cells_after_marking.append(f"('{cell_bbox[0]:.2f}, {cell_bbox[1]:.2f}'), ('{cell_bbox[2]:.2f}, {cell_bbox[3]:.2f}'), '{cell_text}'")
                    else:
                        formatted_cells_after_marking.append(f"{str(None)}, '{cell_text}'" if cell_text else str(None))
                print(f"    Row {row_idx} (After Marking): {formatted_cells_after_marking}")

            # Create structured table with column mapping
            if header_found_in_table:
                structured_table = create_structured_table(table_rows, header_row_index, page_data['words'])
                if structured_table:
                    all_structured_tables.append(structured_table)
                    # print(f"\n    --> Structured Table {table_idx + 1} (Column-Mapped):")
                    # for struct_row_idx, struct_row in enumerate(structured_table):
                    #     print(f"        Row {struct_row_idx}: {struct_row}")

        # Print Word Data (formatted as pdf plumber example)
        print("\n==================================================")
        print("Starting pdf plumber Text and Coordinate Extraction...")
        print("==================================================")
        print(f"\n--- pdf plumber Text and Coordinate Extraction for '{pdf_filename}' ---")
        for word_data in page_data['words']:
            word_text, x0, y0, x1, y1 = word_data
            print(f"Page {page_name.split('_')[1]}, Line: ('{word_text}', x0={{:.2f}}, y0={{:.2f}}, x1={{:.2f}}, y1={{:.2f}})".format(x0, y0, x1, y1))
        
        print("\n==================================================")
        print("PDFPlumber Extraction Complete.")
        print("==================================================")

        # Moved block: Print final marked table for verification at the end of page processing
        if page_data['tables']:
            print(f"\n--- {page_name.replace('_', ' ').capitalize()} Tables (Final Marked Cells) ---")
            for table_idx, table_rows in enumerate(page_data['tables']):
                print(f"    Table {table_idx + 1}:")
                for final_row_idx, final_row_cells in enumerate(table_rows):
                    # Filter out None values
                    final_row_display = [cell_data[1] for cell_data in final_row_cells if cell_data[1] is not None]
                    print(f"{final_row_display}")

    # Print all structured tables collected
    if all_structured_tables:
        print(f"\n--- All Structured Tables (Resolved #$ cells) ---")
        for struct_table_idx, structured_output in enumerate(all_structured_tables):
            print(f"\nTable {struct_table_idx + 1}:")
            for row in structured_output:
                print(row)

if __name__ == "__main__":
    pdf_file_2 = "789.pdf"

    coordinates_2 = extract_pdf_coordinates(pdf_file_2)
    print_formatted_output(coordinates_2, pdf_file_2)