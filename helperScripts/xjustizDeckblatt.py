#!/usr/bin/env python3
from fpdf import FPDF

class CreateDeckblatt():
    
  def __init__(self, xjvObject):
    self.htmlTemplate = f"""
      <p>
        <font face="helvetica" size="30" color="black">
          <b>XJustiz-Deckblatt</b>
        </font>
        <br><br> 
      </p>
      <font face="helvetica" size="12">
      <table border="1" width="100%">   
            <tr>
              <td width="14%"><b>Absender:</b></td>
              <td width="40%" align="left">{xjvObject.absenderText.text()}</td>
              <td width="18%"><b>Absender Az.:</b></td>
              <td width="28%" align="left">{xjvObject.absenderAktenzeichenText.text()}</td>
            </tr>
      </table>  
      <table border="1" width="100%">    
            <tr>
              <td width="14%"><b>Empfänger:</b></td>
              <td width="40%" align="left">{xjvObject.empfaengerText.text()}</td>
              <td width="18%"><b>Empfänger Az.:</b></td>
              <td width="28%" align="left">{xjvObject.empfaengerAktenzeichenText.text()}</td>
            </tr>
      </table>
      <table border="1" width="100%">          
            <tr>
              <td width="14%"><b>Erstellt:</b></td>
              <td width="40%" align="left">{xjvObject.erstellungszeitpunktText.text()}</td>
              <td width="18%"><b>Priorität:</b></td>
              <td width="28%" align="left">{xjvObject.sendungsprioritaetText.text()}</td>
            </tr>  
      </table>
      </font>
      """
    
    instanzenText = xjvObject.instanzenText.toPlainText().replace("\n", "<br>")
    if len(instanzenText) > 0:  
      self.htmlTemplate += f"""  
        
          <font face="helvetica" size="12">
            {instanzenText}
          </font>
        <br>
        """
    
    beteiligtenText = xjvObject.beteiligteText.toPlainText().replace("\n", "<br>")     
    if len(beteiligtenText) > 0:  
      self.htmlTemplate += f"""
        <section>
          <font face="helvetica" size="12" color="black">
            _______________________________________<br><br>
            Beteiligte<br>
            _______________________________________<br><br> 
            {beteiligtenText}
          </font>
        </section>
        """
   
  def output(self, filename):
    if filename:
      pdf = FPDF()
      pdf.add_page()
      pdf.write_html(self.htmlTemplate)
      pdf.output(filename)
      return filename
    
    return None