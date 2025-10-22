#!/usr/bin/env python3
from fpdf import FPDF, FontFace, XPos, YPos
from os import path

class CreateDeckblatt():
    
  def __init__(self, xjvObject):
   
    self.instanzen_text  = xjvObject.instanzenText.toPlainText()  
    self.beteiligte_text = xjvObject.beteiligteText.toPlainText()
    self.notizen_text    = xjvObject.notizenText.toPlainText()
    self.export_notizen  = xjvObject.actionNotizenaufDeckblattausgeben.isChecked()

    first_thee_column_widths = (28,80,35)
    self.column_widths = (*first_thee_column_widths, 190-sum(first_thee_column_widths))
    
    self.table_content=(
      ('Absender:', xjvObject.absenderText.text(),'Absender Az.:', xjvObject.absenderAktenzeichenText.text()),
      ('Empfänger:', xjvObject.empfaengerText.text(),'Empfänger Az.:', xjvObject.empfaengerAktenzeichenText.text()),
      ('Erstellt:', xjvObject.erstellungszeitpunktText.text(),'Priorität:', xjvObject.sendungsprioritaetText.text())
    )
    
  def print_section(self, pdf, heading, content, vertical_space_between_sections = 5):    
    pdf.set_fill_color(225)
    if len(content) > 0:
      pdf.set_y(pdf.get_y() + vertical_space_between_sections)
      with pdf.use_font_face(FontFace(emphasis="BOLD")):
        pdf.multi_cell(w = 0, border = 0, fill = True,  text=heading, new_x=XPos.LEFT, new_y=YPos.NEXT, padding=1)  
      pdf.multi_cell(w = 0, border = 0, text = content, markdown=True, new_x=XPos.LEFT, new_y=YPos.NEXT, padding=1)   
      
  def output(self, filename):
    if filename:
      pdf = FPDF()
      pdf.add_font('Ubuntu', fname=path.join(path.dirname(path.realpath(__file__)), '..', 'fonts', 'ubuntu-font-family-0.83', 'Ubuntu-R.ttf'))
      pdf.add_font('Ubuntu', style ='B', fname=path.join(path.dirname(path.realpath(__file__)), '..', 'fonts', 'ubuntu-font-family-0.83', 'Ubuntu-B.ttf'))
      pdf.add_font('Ubuntu', style ='I', fname=path.join(path.dirname(path.realpath(__file__)), '..', 'fonts', 'ubuntu-font-family-0.83', 'Ubuntu-RI.ttf'))
      pdf.add_font('Ubuntu', style ='BI', fname=path.join(path.dirname(path.realpath(__file__)), '..', 'fonts', 'ubuntu-font-family-0.83', 'Ubuntu-BI.ttf'))
      pdf.set_font("Ubuntu", size = 12)
      
      pdf.add_page()
      # Überschrift
      with pdf.use_font_face(FontFace(emphasis="BOLD", size_pt = 32)):
          pdf.write(text='Deckblatt\n')  
      
      # Meta-Daten-Tabelle    
      bold_style = FontFace(emphasis="BOLD")
      with pdf.table(line_height=pdf.font_size, col_widths=self.column_widths, padding=2, first_row_as_headings=False) as table:
        for row_content in self.table_content:
          row = table.row()
          for column_no in range(len(row_content)):
            column_width = self.column_widths[column_no]
            if column_no % 2 == 0:
              row.cell(row_content[column_no], style = bold_style)
            else:
              row.cell(row_content[column_no])
      
      # Restliche Inhalte
      if self.export_notizen:
        self.print_section(pdf, 'Notizen:', self.notizen_text)
      self.print_section(pdf, 'Instanzdaten:', self.instanzen_text)
      self.print_section(pdf, 'Beteiligtendaten:', self.beteiligte_text)
          
      pdf.output(filename)
      return filename
    
    return None