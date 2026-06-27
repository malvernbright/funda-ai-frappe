# Copyright (c) 2026, ByteSphere Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class CurriculumMaterial(Document):
    def on_update(self):
        # Trigger the embedding job only if there is a file and it's not already processing/indexed
        if self.material_file and self.indexing_status not in ["Processing", "Indexed"]:
            # Set status to Processing immediately
            frappe.db.set_value("Curriculum Material", self.name, "indexing_status", "Processing")
            
            # Enqueue the background job to the 'long' queue (timeout: 1500 seconds)
            # This ensures large PDFs don't timeout on edge hardware
            frappe.enqueue(
                "funda_ai.funda_ai.utils.vector_ingestion.process_curriculum_file",
                queue="long",
                timeout=1500,
                doc_name=self.name,
                file_url=self.material_file,
                tier=self.tier
            )
