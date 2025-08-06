import pdfplumber

pdf_path = "123.pdf"

with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages, start=1):
        print(f"\n--- Page {i} ---")
        tables = page.extract_tables()
        if not tables:
            print("No tables found.")
        for table_num, table in enumerate(tables, start=1):
            print(f"\nTable {table_num}:")
            for row in table:
                print(row)
