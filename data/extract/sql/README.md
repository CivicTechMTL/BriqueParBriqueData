# Data Engineering

## What

The SQL scripts contained within are examples, used to extract/transform/load Quebec geodata (specifically lot/building and zoning information) into a consistent schema.

The general process for doing so:

1. Get the data by request to relevant authorities (each arrondissement for zoning, province for lots)
2. Load the data into `duckdb` (see [load_data.sql](./load_data.sql))
3. Create view for each lot that includes zoning code by spatial join (see [create_view.sql](./create_view.sql))
4. `UNION` all of the views together (see [create_view.all_lots.sql](./create_view.all_lots.sql))

## Usage

As of this writing (2026-08-12), the current opportunity being pursued is generating a mailing list based on several zoning and location factors; see [mailing_list.sql](mailing_list.sql) for details.