USE datacleanpro;

ALTER TABLE cleaning_history
ADD COLUMN cleaned_file_id CHAR(32) NULL;

CREATE UNIQUE INDEX uq_cleaning_history_cleaned_file_id
ON cleaning_history (cleaned_file_id);