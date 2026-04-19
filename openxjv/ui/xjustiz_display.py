#!/usr/bin/env python3
# coding: utf-8
"""
XJustiz Display Renderer Module.

This module provides rendering functionality for displaying XJustiz data structures
in HTML format. It handles all template rendering for instances, parties, persons,
organizations, appointments, and related data.

The XJustizDisplayRenderer class contains methods for converting structured XJustiz
data into formatted HTML for display in the UI.
"""

from typing import Dict, List, Any, Optional, Union
from .helpers import TextObject


class XJustizDisplayRenderer:
    """
    Renderer class for converting XJustiz data structures to formatted HTML.

    This class provides template methods for rendering various XJustiz entities
    including natural persons, organizations, law offices, appointments, and
    administrative data. All methods generate HTML output suitable for display
    in Qt web engine widgets.

    Attribute:
        akte: The current case file (Akte) object containing all case data
    """

    def __init__(self, akte: Any) -> None:
        """
        Initialize the XJustiz display renderer.

        Args:
            akte: The case file object containing grunddaten, beteiligtenverzeichnis,
                  rollenverzeichnis, and other case-related data
        """
        self.akte = akte

    def render_instances_view(self) -> str:
        """
        Render the instances (court instances) view.

        Generates HTML representation of all court instances including case numbers,
        departments, subject matter, and telecommunications data.

        Returns:
            Formatted HTML string containing all instance data

        Note:
            If cached plain text is available in extensions, returns that instead
        """
        try:
            if self.akte.erweiterungen.get('openXJV_instanzdaten_klartext'):
                return self.akte.erweiterungen['openXJV_instanzdaten_klartext']['text']
        except AttributeError:
            pass

        text = TextObject()
        single_values = [
            'abteilung',
            'kurzrubrum',
            'verfahrensinstanznummer',
            'sachgebiet',
            'sachgebietszusatz'
        ]

        if self.akte.grunddaten.get('verfahrensnummer'):
            text.add_line('<b><i>Verfahrensnummer</i></b>', self.akte.grunddaten['verfahrensnummer'])

        keys = list(self.akte.grunddaten['instanzen'].keys())
        for key in keys:
            instanz = self.akte.grunddaten['instanzen'][key]
            hr = '_______________________________________<br><br>'
            text.add_raw(f"{hr}<b>Instanz {key}</b><br>{hr}<b><i>Instanzdaten</i></b><br>")

            if instanz.get('auswahl_instanzbehoerde'):
                text.add_line('<b>Behörde</b>', instanz['auswahl_instanzbehoerde'].get('name'))

            if instanz.get('aktenzeichen'):
                text.add_line('<b>Aktenzeichen</b>', instanz['aktenzeichen'].get('aktenzeichen.freitext'))
                text.add_line('<b>Sammelvorgangsnummer</b>', instanz['aktenzeichen'].get('sammelvorgangsnummer'))

            for field_name in single_values:
                if instanz.get(field_name):
                    value = instanz[field_name]
                    label = field_name.replace('_', ' ').capitalize()
                    text.add_raw(f'<b>{label}:</b> {value}<br>')

            for gegenstand in instanz['verfahrensgegenstand']:
                set_br = False
                if gegenstand.get('gegenstand'):
                    text.add_raw(f"<b>Gegenstand:</b> {gegenstand['gegenstand']}")
                    set_br = True
                if gegenstand.get('gegenstandswert').strip():
                    text.add_raw(f", Streitwert: {gegenstand['gegenstandswert']}")
                    set_br = True
                if gegenstand.get('auswahl_zeitraumDesVerwaltungsaktes').strip():
                    text.add_raw(f", Datum/Zeitraum: {gegenstand['auswahl_zeitraumDesVerwaltungsaktes']}")
                    set_br = True
                if set_br:
                    text.add_raw('<br>')

            text.add_raw(self.render_telecommunications(instanz['telekommunikation']))

        return text.get_text()

    def render_telecommunications(self, telekommunikation: List[Dict[str, str]]) -> str:
        """
        Render telecommunications connections template.

        Args:
            telekommunikation: List of telecommunications entries with type and connection data

        Returns:
            Formatted HTML string containing telecommunications data
        """
        text = TextObject()
        text.add_heading('Telekommunikationsverbindungen')
        for eintrag in telekommunikation:
            text.add_raw(f"{eintrag.get('telekommunikationsart')}: {eintrag.get('verbindung')}")
            if eintrag.get('telekommunikationszusatz'):
                text.add_raw(f" ({eintrag['telekommunikationszusatz']})")
            text.add_raw('<br>')
        return text.get_text()

    def render_roles(self, rollen: List[Dict[str, Any]]) -> str:
        """
        Render roles template.

        Generates HTML for party roles including role numbers, designations,
        and references to other parties.

        Args:
            rollen: List of role dictionaries containing role information

        Returns:
            Formatted HTML string containing role information
        """
        text = ''
        for rolle in rollen:
            text += '<b>Rolle'
            if rolle.get('rollenID'):
                text += ' in Instanz '
                delimiter = ''
                for rollenID in rolle['rollenID']:
                    text += f"{delimiter}{rollenID.get('ref.instanznummer')}"
                    delimiter = ', '
                text += f":</b> <u>{self.akte.rollenverzeichnis.get(str(rolle.get('rollennummer')))}</u><br>"
            else:
                if rolle.get('rollenbezeichnung'):
                    text += f":</b> {rolle.get('rollenbezeichnung')} {rolle.get('nr')}<br>"
                else:
                    text += '</b><br>'

            if rolle.get('naehereBezeichnung'):
                text += f"Nähere Bezeichnung: {rolle['naehereBezeichnung']}<br>"
            if rolle.get('sonstigeBezeichnung'):
                for bezeichnung in rolle.get('sonstigeBezeichnung'):
                    text += f"Sonstige Bezeichnung: {bezeichnung}<br>"
            if rolle.get('dienstbezeichnung'):
                for bezeichnung in rolle.get('dienstbezeichnung'):
                    text += f"Dienstbezeichnung: {bezeichnung}<br>"
            if rolle.get('referenz'):
                for referenz in rolle.get('referenz'):
                    text += f"Bezug zu: {self.akte.rollenverzeichnis.get(str(referenz))}<br>"
            if rolle.get('geschaeftszeichen'):
                text += f"Geschäftszeichen: {rolle['geschaeftszeichen']}<br>"
        return text

    def render_address(self, anschriften: Union[Dict[str, Any], List[Dict[str, Any]]],
                      heading: str = 'Postalische Anschrift') -> str:
        """
        Render postal address template.

        Args:
            anschriften: Single address dict or list of address dicts
            heading: Section heading text (default: 'Postalische Anschrift')

        Returns:
            Formatted HTML string containing address information
        """
        if not isinstance(anschriften, list):
            anschriften = [anschriften]

        items = {
            'erfassungsdatum': 'Erfasst am',
            'wohnungsgeber': 'Wohnungsgeber'
        }
        text = ''

        delimiter = ''
        for anschrift in anschriften:
            text += delimiter
            if anschrift.get('anschriftstyp'):
                text += f"<u>{anschrift['anschriftstyp']}</u><br>"

            if anschrift.get('derzeitigerAufenthalt') and anschrift.get('derzeitigerAufenthalt').lower() == 'true':
                text += 'Hierbei handelt es sich um den derzeitigen Aufenthalt.<br>'

            for key, label in items.items():
                if anschrift[key]:
                    text += f"{label}: {anschrift[key]}<br>"

            if anschrift.get('strasse') or anschrift.get('hausnummer'):
                text += f"{anschrift.get('strasse')} {anschrift.get('hausnummer')}<br>"
            if anschrift.get('anschriftenzusatz'):
                delimiter_inner = ''
                for zusatz in anschrift['anschriftenzusatz']:
                    text += delimiter_inner + zusatz
                    delimiter_inner = ', '
                text += '<br>'
            if anschrift.get('postfachnummer'):
                text += f"Postfach {anschrift['postfachnummer']}<br>"
            if anschrift.get('postleitzahl') or anschrift.get('ort'):
                text += f"{anschrift.get('postleitzahl')} {anschrift.get('ort')} {anschrift.get('ortsteil')}<br>"
            if anschrift.get('staat'):
                text += f"{anschrift['staat']}<br>"
            if anschrift.get('bundesland'):
                text += f"{anschrift['bundesland']}<br>"
            delimiter = '<br>'

        if text:
            text = f'<br><b><i>{heading}</i></b><br>{text}'
        return text

    def render_full_name(self, voller_name: Dict[str, Any]) -> str:
        """
        Render full name template for natural persons.

        Includes current name, birth name, former names, and name prefixes.

        Args:
            voller_name: Dictionary containing name components

        Returns:
            Formatted HTML string containing full name information
        """
        text = ''
        name_components = [
            'titel',
            'vorname',
            'namensvorsatz',
            'nachname',
            'namenszusatz'
        ]

        birth_name_components = [
            'geburtsnamensvorsatz',
            'geburtsname',
        ]

        if voller_name['vorname'] or voller_name['nachname']:
            text += 'Voller Name:'
            for component in name_components:
                if voller_name[component] is None or not voller_name[component]:
                    continue
                elif component == 'nachname' or component == 'namensvorsatz':
                    text += f" <u>{voller_name[component]}</u>"
                else:
                    text += f" {voller_name[component]}"
            text += '<br>'

        if voller_name['rufname']:
            text += f"Rufname: {voller_name['rufname']}<br>"

        if voller_name['geburtsname']:
            text += 'Geburtsname:'
            for component in birth_name_components:
                if voller_name[component] is None or not voller_name[component]:
                    continue
                else:
                    text += f" {voller_name[component]}"
            text += '<br>'

        for weiterer_name in voller_name['vorname.alt']:
            text += f"Weiterer Name: {weiterer_name}<br>"

        for alt_vorname in voller_name['vorname.alt']:
            text += f"Ehemaliger Vorname: {alt_vorname}<br>"

        for alt_name in voller_name['nachname.alt']:
            text += f"Ehemaliger Nachname: {alt_name}<br>"
        return text

    def render_law_office(self, beteiligter: Dict[str, Any]) -> str:
        """
        Render law office/attorney template.

        Args:
            beteiligter: Dictionary containing law office data

        Returns:
            Formatted HTML string containing law office information
        """
        text = '<br><b><u>Kanzlei / Rechtsanwalt</u></b><br>'

        if beteiligter.get('bezeichnung.aktuell'):
            text += f"Bezeichnung: {beteiligter['bezeichnung.aktuell']}<br>"

        for alte_bezeichnung in beteiligter['bezeichnung.alt']:
            text += f"Ehemals: {alte_bezeichnung}<br>"

        if beteiligter.get('kanzleiform'):
            text += f"Kanzleiform: {beteiligter['kanzleiform']}<br>"

            if beteiligter.get('rechtsform'):
                text += f"Rechtsform: {beteiligter['rechtsform']}<br>"

        if beteiligter.get('geschlecht'):
            text += f"Geschlecht: {beteiligter['geschlecht']}<br>"

        text += self.render_address(beteiligter['anschrift'])

        text += self.render_telecommunications(beteiligter['telekommunikation'])

        if beteiligter.get('bankverbindung'):
            text += self.render_bank_details(beteiligter['bankverbindung'])

        if beteiligter.get('umsatzsteuerID'):
            text += '<br><b><i>Steuerdaten</i></b><br>'
            text += f"Umsatzsteuer-ID: {beteiligter['umsatzsteuerID']}<br>"

        if beteiligter.get('raImVerfahren'):
            ra_daten = self.render_natural_person(beteiligter['raImVerfahren'])
            if ra_daten:
                text += f"<blockquote><b><u>Rechtsanwalt im Verfahren</u></b>{ra_daten}</blockquote>"

        return text

    def render_organization(self, beteiligter: Dict[str, Any]) -> str:
        """
        Render organization/legal entity template.

        Args:
            beteiligter: Dictionary containing organization data

        Returns:
            Formatted HTML string containing organization information
        """
        text = '<br><b><u>Organisation / Juristische Person</u></b><br>'
        if beteiligter.get('bezeichnung.aktuell'):
            text += f"Bezeichnung: {beteiligter['bezeichnung.aktuell']}</b><br>"

        for alte_bezeichnung in beteiligter['bezeichnung.alt']:
            text += f"Ehemals: {alte_bezeichnung}<br>"

        if beteiligter.get('kurzbezeichnung'):
            text += f"Kurzbezeichnung: {beteiligter['kurzbezeichnung']}<br>"

        if beteiligter.get('geschlecht'):
            text += f"Geschlecht: {beteiligter['geschlecht']}<br>"

        if beteiligter.get('angabenZurRechtsform'):
            text += self.render_legal_form(beteiligter['angabenZurRechtsform'])

        for sitz in beteiligter['sitz']:
            text += self.render_headquarters(sitz)

        text += self.render_address(beteiligter['anschrift'])
        text += self.render_telecommunications(beteiligter['telekommunikation'])

        if beteiligter.get('bundeseinheitlicheWirtschaftsnummer'):
            text += '<br><b><i>Bundeseinheitliche Wirtschaftsnummer</i></b><br>'
            text += f"Bundeseinheitliche Wirtschaftsnr.: {beteiligter['bundeseinheitlicheWirtschaftsnummer']}<br>"

        if beteiligter.get('registereintragung'):
            text += self.render_registry_data(beteiligter['registereintragung'])

        if beteiligter.get('bankverbindung'):
            text += self.render_bank_details(beteiligter['bankverbindung'])

        if beteiligter.get('umsatzsteuerID'):
            text += '<br><b><i>Steuerdaten</i></b><br>'
            text += f"Umsatzsteuer-ID: {beteiligter['umsatzsteuerID']}<br>"

        if beteiligter.get('vorsteuerabzugsberechtigt'):
            text += '<br><b><i>Vorsteuerinformation</i></b><br>'
            if beteiligter['vorsteuerabzugsberechtigt'] == 'true':
                text += 'Zum Vorsteuerabzug berechtigt.<br>'
            else:
                text += 'Nicht zum Abzug der Vorsteuer berechtigt.<br>'

        return text

    def render_headquarters(self, sitz: Dict[str, str]) -> str:
        """
        Render headquarters/seat location template.

        Args:
            sitz: Dictionary containing seat location data

        Returns:
            Formatted HTML string containing headquarters information
        """
        text = TextObject()
        text.add_heading('Sitz')
        text.add_line('Ort', sitz.get('ort'))
        text.add_line('Postleitzahl', sitz.get('postleitzahl'))
        text.add_line('Staat', sitz.get('staat'))

        return text.get_text()

    def render_legal_form(self, rechtsform: Dict[str, str]) -> str:
        """
        Render legal form template.

        Args:
            rechtsform: Dictionary containing legal form data

        Returns:
            Formatted HTML string containing legal form information
        """
        text = TextObject()
        text.add_heading('Rechtsform')
        text.add_line('Rechtsform', rechtsform.get('rechtsform'))
        text.add_line('Weitere Bezeichnung', rechtsform.get('weitereBezeichnung'))

        return text.get_text()

    def render_natural_person(self, beteiligter: Dict[str, Any]) -> str:
        """
        Render natural person template.

        Includes personal data, addresses, tax information, birth/death data,
        ID documents, and more.

        Args:
            beteiligter: Dictionary containing natural person data

        Returns:
            Formatted HTML string containing person information
        """
        text = TextObject()
        text.add_heading('Personendaten')
        text.add_raw(self.render_full_name(beteiligter.get('vollerName')))

        for staatsangehoerigkeit in beteiligter['staatsangehoerigkeit']:
            text.add_line('Staatsangehörigkeit', staatsangehoerigkeit)

        for herkunftsland in beteiligter['herkunftsland']:
            text.add_line('Herkunftsland', herkunftsland)

        for sprache in beteiligter['sprache']:
            text.add_line('Sprache', sprache)

        if beteiligter.get('beruf'):
            text.add_raw('<br><b><i>Berufliche Daten</i></b><br>')
            for beruf in beteiligter['beruf']:
                text.add_line('Beruf', beruf)

        text.add_raw(self.render_address(beteiligter.get('anschrift')))
        text.add_raw(self.render_telecommunications(beteiligter.get('telekommunikation')))

        if beteiligter.get('zustaendigeInstitution'):
            text.add_raw('<br><b><i>Zuständige Institution(en)</i></b><br>')
            for rollennummer in beteiligter['zustaendigeInstitution']:
                text.add_raw(f"{self.akte.rollenverzeichnis.get(str(rollennummer))}<br>")

        if beteiligter.get('bankverbindung'):
            text.add_raw(self.render_bank_details(beteiligter['bankverbindung']))

        if beteiligter.get('bundeseinheitlicheWirtschaftsnummer'):
            text.add_raw('<br><b><i>Bundeseinheitliche Wirtschaftsnummer</i></b><br>')
            text.add_line('Wirtschaftsnummer', beteiligter['bundeseinheitlicheWirtschaftsnummer'])

        if beteiligter.get('umsatzsteuerID') or beteiligter.get('steueridentifikationsnummer') or beteiligter.get('vorsteuerabzugsberechtigt'):
            text.add_raw('<br><b><i>Steuerdaten</i></b><br>')
            if beteiligter.get('umsatzsteuerID'):
                text.add_line('Umsatzsteuer-ID', beteiligter.get('umsatzsteuerID'))
            if beteiligter.get('steueridentifikationsnummer'):
                text.add_line('Steueridentifikationsnummer', beteiligter.get('steueridentifikationsnummer'))
            if beteiligter.get('vorsteuerabzugsberechtigt'):
                text.add_line('Vorsteuerabzug', 'Zum Abzug der Vorsteuer berechtigt' if beteiligter['vorsteuerabzugsberechtigt'] == 'true' else 'Nicht zum Abzug der Vorsteuer berechtigt')

        for alias in beteiligter.get('aliasNatuerlichePerson'):
            text.add_raw(f"<blockquote><b><u>Aliasdaten</u></b>{self.render_natural_person(alias)}</blockquote>")

        if beteiligter.get('geburt'):
            text.add_raw(self.render_birth_data(beteiligter['geburt']))

        if beteiligter.get('tod'):
            text.add_raw(self.render_death_data(beteiligter['tod']))

        if beteiligter.get('ausweisdokument'):
            text.add_raw(self.render_id_documents(beteiligter['ausweisdokument']))

        if beteiligter.get('registereintragungNatuerlichePerson'):
            text.add_raw(self.render_registry_entry(beteiligter['registereintragungNatuerlichePerson']))

        if beteiligter.get('auswahl_auskunftssperre'):
            text.add_raw(self.render_access_restriction(beteiligter['auswahl_auskunftssperre']))

        return text.get_text()

    def render_id_documents(self, ausweise: List[Dict[str, Any]]) -> str:
        """
        Render ID documents template.

        Args:
            ausweise: List of ID document dictionaries

        Returns:
            Formatted HTML string containing ID document information
        """
        text = TextObject()
        text.add_heading('Ausweisdokumente')
        for ausweis in ausweise:
            if text.get_text():
                text.add_raw('<br>')
            text.add_line('Ausweisart', ausweis.get('ausweisart'))
            text.add_line('Ausweis-ID', ausweis.get('ausweis.ID'))
            text.add_line('Ausstellender Staat', ausweis.get('ausstellenderStaat'))
            if ausweis.get('ausstellendeBehoerde'):
                text.add_line('Ausstellende Behörde', self.resolve_authority(ausweis['ausstellendeBehoerde']))
            if ausweis.get('gueltigkeit'):
                text.add_line('Gültigkeit', self.resolve_time_period(ausweis['gueltigkeit']))
            text.add_line('Zusatzinformationen', ausweis.get('zusatzinformation'))
        return text.get_text()

    def resolve_time_period(self, zeitraum: Dict[str, str]) -> str:
        """
        Resolve time period to display string.

        Args:
            zeitraum: Dictionary with 'beginn' and/or 'ende' keys

        Returns:
            Formatted time period string (e.g., "2020-01-01 - 2025-12-31")
        """
        text = ''
        if zeitraum.get('beginn'):
            text += zeitraum['beginn']
        if zeitraum.get('ende'):
            if text:
                text += ' - '
            text += zeitraum['ende']
        return text

    def resolve_authority(self, behoerde: Dict[str, str]) -> str:
        """
        Resolve authority reference to name.

        Args:
            behoerde: Authority dictionary with type and name

        Returns:
            Authority name (resolved from party registry if reference)
        """
        if behoerde.get('type') == 'GDS.Ref.Beteiligtennummer':
            return self.akte.beteiligtenverzeichnis.get(behoerde.get('name'))
        else:
            return behoerde.get('name')

    def render_registry_entry(self, registereintragung: Dict[str, Any]) -> str:
        """
        Render registry entry for natural person template.

        Args:
            registereintragung: Dictionary containing registry entry data

        Returns:
            Formatted HTML string containing registry entry information
        """
        text = TextObject()

        text.add_heading('Registrierung natürliche Person')

        text.add_line('Firma', registereintragung.get('verwendeteFirma'))
        text.add_line('Weitere Bezeichnung', registereintragung['angabenZurRechtsform'].get('weitereBezeichnung'))
        text.add_line('Rechtsform', registereintragung['angabenZurRechtsform'].get('rechtsform'))

        if registereintragung.get('registereintragung'):
            text.add_raw(self.render_registry_data(registereintragung['registereintragung']))

        return text.get_text()

    def render_registry_data(self, registrierung: Dict[str, Any]) -> str:
        """
        Render registry data template.

        Args:
            registrierung: Dictionary containing registration data

        Returns:
            Formatted HTML string containing registry information
        """
        text = TextObject()

        text.add_heading('Registrierungsdaten')

        items = (
            ['registernummer', 'Registernummer'],
            ['reid', 'REID'],
            ['lei', 'LEI'],
            ['euid', 'EUID']
        )

        for item in items:
            text.add_line(item[1], registrierung[item[0]])

        text.add_line('Registergericht', registrierung['auswahl_registerbehoerde']['inlaendischesRegistergericht']['gericht'])
        text.add_line('Registerart', registrierung['auswahl_registerbehoerde']['inlaendischesRegistergericht']['registerart'])
        text.add_line('Ausländische Registerbehörde', registrierung['auswahl_registerbehoerde'].get('auslaendischeRegisterbehoerde'))
        text.add_line('Ausländische Registerbehörde (lokaler Name)', registrierung['auswahl_registerbehoerde'].get('auslaendischeRegisterbehoerdeName'))
        text.add_line('Registerbehörde', registrierung['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbehoerde'])
        text.add_line('Registerbezeichnung', registrierung['auswahl_registerbehoerde']['sonstigeRegisterbehoerde']['registerbezeichnung'])

        return text.get_text()

    def render_access_restriction(self, sperre: Dict[str, Any]) -> str:
        """
        Render access restriction/information blocking template.

        Args:
            sperre: Dictionary containing access restriction data

        Returns:
            Formatted HTML string containing access restriction information
        """
        text = TextObject()

        text.add_heading('Auskunftssperrdaten')

        if sperre['auskunftssperre.vorhanden'].lower() == 'true':
            text.add_raw('Auskunftssperre vorhanden: ja<br>')
        elif sperre['auskunftssperre.vorhanden'].lower() == 'false':
            text.add_raw('Auskunftssperre vorhanden: nein<br>')

        items = [
            'grundlage',
            'umfang',
            'sperrstufe'
        ]

        for item in items:
            text.add_line(item.capitalize(), sperre['auskunftssperre.details'][item])

        return text.get_text()

    def render_birth_data(self, geburt: Dict[str, Any]) -> str:
        """
        Render birth data template.

        Args:
            geburt: Dictionary containing birth information

        Returns:
            Formatted HTML string containing birth data
        """
        text = TextObject()
        text.add_heading('Geburtsdaten')
        text.add_line('Geburtsdatum', geburt.get('geburtsdatum'))
        if geburt['geburtsdatum.unbekannt'].lower() == 'true':
            text.add_raw('Geburtsdatum: unbekannt<br>')
        text.add_line('Geburtsort', geburt['geburtsort']['ort'])
        text.add_line('Staat des Geburtsortes', geburt['geburtsort']['staat'])
        text.add_line('Geburtsname der Mutter', geburt['geburtsname.mutter'])

        if geburt.get('geburtsname.vater'):
            # Value was introduced in version 3.6.2
            text.add_line('Geburtsname des Vaters', geburt['geburtsname.vater'])

        items = [
            ['nachname.vater', 'Nachname des Vaters'],
            ['vorname.vater', 'Vorname des Vaters'],
            ['nachname.mutter', 'Nachname der Mutter'],
            ['vorname.mutter', 'Vorname der Mutter']
        ]

        for item in items:
            if geburt['name.eltern'][item[0]]:
                for name in geburt['name.eltern'][item[0]]:
                    text.add_line(item[1], name)

        return text.get_text()

    def render_death_data(self, tod: Dict[str, Any]) -> str:
        """
        Render death data template.

        Args:
            tod: Dictionary containing death information

        Returns:
            Formatted HTML string containing death data
        """
        text = TextObject()
        text.add_heading('Sterbedaten')
        items = [
            ['sterbedatum', 'Sterbedatum'],
            ['sterbestandesamtBehoerdennummer', 'Behördennummer des Standesamts'],
            ['sterbestandesamtName', 'Names des Standesamts'],
            ['sterberegisternummer', 'Sterberegisternr.'],
            ['eintragungsdatum', 'Eintragungsdatum'],
            ['sterberegisterart', 'Sterberegisterart'],
            ['todErklaert', 'Tod erklärt']
        ]

        sterbezeitraum = ''
        if tod['sterbedatumZeitraum']['beginn']:
            sterbezeitraum = tod['sterbedatumZeitraum']['beginn']
        if tod['sterbedatumZeitraum']['ende']:
            sterbezeitraum += f" - {tod['sterbedatumZeitraum']['ende']}"

        text.add_line('Sterbezeitraum', sterbezeitraum)

        for item in items:

            item_value = tod[item[0]]

            if item[0] == 'todErklaert' and item_value.lower() == 'true':
                item_value = 'ja'
            elif item[0] == 'todErklaert' and item_value.lower() == 'false':
                item_value = 'nein'

            text.add_line(item[1], item_value)

        if tod['sterbeort']:
            text.add_raw(self.render_address([tod['sterbeort']], 'Sterbeort'))

        return text.get_text()

    def render_bank_details(self, bankverbindungen: List[Dict[str, Any]]) -> str:
        """
        Render bank account details template.

        Args:
            bankverbindungen: List of bank account dictionaries

        Returns:
            Formatted HTML string containing bank account information
        """
        text = TextObject()
        text.add_heading('Bankverbindungsdaten')
        items = [
            ['bankverbindungsnummer', 'Bankverbindungsnummer'],
            ['iban', 'IBAN'],
            ['bic', 'BIC'],
            ['bank', 'Bank'],
            ['kontoinhaber', 'Kontoinhaber'],
            ['sepa-mandat', 'Sepa-Mandat'],
            ['verwendungszweck', 'Verwendungszweck']
        ]
        verbindung_nr = 1
        for bankverbindung in bankverbindungen:
            for item in items:

                item_value = bankverbindung.get(item[0])

                if item[0] == 'sepa-mandat' and item_value.lower() == 'true':
                    item_value = 'Erteilt'
                elif item[0] == 'sepa-mandat' and item_value.lower() == 'false':
                    item_value = 'Nicht erteilt'

                text.add_line(item[1], item_value)

            if bankverbindung.get('sepa-basislastschrift'):
                text.add_line('Lastschrifttyp', bankverbindung['sepa-basislastschrift'].get('lastschrifttyp'))
                text.add_line('Mandatsreferenz', bankverbindung['sepa-basislastschrift'].get('mandatsreferenz'))
                text.add_line('Mandatsdatum', bankverbindung['sepa-basislastschrift'].get('mandatsdatum'))

            if verbindung_nr < len(bankverbindungen):
                text.add_raw('<br>')
            verbindung_nr += 1

        return text.get_text()

    def render_parties_view(self) -> str:
        """
        Render the parties (involved parties) view.

        Generates HTML representation of all parties involved in the case,
        including their roles and detailed information.

        Returns:
            Formatted HTML string containing all party data

        Note:
            If cached plain text is available in extensions, returns that instead
        """
        try:
            if self.akte.erweiterungen.get('openXJV_beteiligung_klartext'):
                return self.akte.erweiterungen['openXJV_beteiligung_klartext']['text']
        except AttributeError:
            pass

        text = TextObject()
        for beteiligung in self.akte.grunddaten['beteiligung']:
            text.add_line('<b>Beteiligtennummer</b>', beteiligung.get('beteiligtennummer'))

            if beteiligung['rolle']:
                text.add_raw(self.render_roles(beteiligung['rolle']))

            beteiligter = beteiligung['beteiligter']

            beteiligtentyp = beteiligter.get('type')
            if beteiligtentyp == 'GDS.Organisation':
                text.add_raw(self.render_organization(beteiligter))
            elif beteiligtentyp == 'GDS.RA.Kanzlei':
                text.add_raw(self.render_law_office(beteiligter))
            elif beteiligtentyp == 'GDS.NatuerlichePerson':
                text.add_raw(self.render_natural_person(beteiligter))
            text.add_raw('_______________________________________<br><br>')

        return text.get_text()

    def render_appointment(self, termin: Dict[str, Any]) -> str:
        """
        Render appointment/hearing details template.

        Args:
            termin: Dictionary containing appointment data

        Returns:
            Formatted HTML string containing appointment information
        """
        text = TextObject()
        text.add_heading('Terminsdetails')
        hr = '________________________________________________________________________________________________<br><br>'

        # Old continuation appointment values (before version 3.4.1)
        if termin.get('hauptterminsdatum'):
            if termin['auswahl_hauptterminszeit']['hauptterminsuhrzeit']:
                zeit = f"{termin['auswahl_hauptterminszeit']['hauptterminsuhrzeit']} Uhr"
            else:
                zeit = termin['auswahl_hauptterminszeit']['hauptterminszeit']
            text.add_raw(f"Fortsetzungstermin des Haupttermins vom {termin['hauptterminsdatum']}, {zeit}<br>")
            if termin['hauptterminsID']:
                text.add_line('Haupttermins-ID', termin['hauptterminsID'])

        # New continuation appointment values (from version 3.4.1 onwards)
        if termin.get('terminskategorie'):
            text.add_line('Terminskategorie', termin['terminskategorie'])
        if termin.get('ref.bezugstermin'):
            text.add_line('Bezieht sich auf ursprüngliche Termins-ID', termin['ref.bezugstermin'])

        text.add_line('Termins-ID', termin['terminsID'])

        if termin['terminsart']:
            text.add_raw(f"<b>Art des Termins: {termin['terminsart']}</b><br>")

        text.add_line('Spruchkörper', termin.get('spruchkoerper'))

        if termin['oeffentlich'].lower() == 'true':
            text.add_raw("Es handelt sich um einen öffentlichen Termin.<br>")
        elif termin['oeffentlich'].lower() == 'false':
            text.add_raw("Dieser Termin ist nicht öffentlich.<br>")

        datum = termin['terminszeit']['terminsdatum']
        if termin['terminszeit']['auswahl_terminszeit']['terminsuhrzeit']:
            zeit = f"{termin['terminszeit']['auswahl_terminszeit']['terminsuhrzeit']} Uhr"
        else:
            zeit = termin['terminszeit']['auswahl_terminszeit']['terminszeitangabe']
        text.add_raw(f"<b>Termin: {datum}, {zeit}</b><br>")

        if termin['terminszeit']['terminsdauer']:
            text.add_line('Angesetzte Dauer', f"{termin['terminszeit']['terminsdauer']} h")

        gerichtsort = TextObject()
        if termin['auswahl_terminsort']['gerichtsort']['anschrift']:
            gerichtsort.add_raw(self.render_address(termin['auswahl_terminsort']['gerichtsort']['anschrift'], heading='Terminsort'))
        gerichtsort.add_line('Gebäude', termin['auswahl_terminsort']['gerichtsort']['gebaeude'])
        gerichtsort.add_line('Stockwerk', termin['auswahl_terminsort']['gerichtsort']['stockwerk'])
        gerichtsort.add_line('Raum', termin['auswahl_terminsort']['gerichtsort']['raum'])
        if gerichtsort.get_text():
            text.add_raw(gerichtsort.get_text())

        lokaltermin = TextObject()
        if termin['auswahl_terminsort']['lokaltermin']['anschrift']:
            lokaltermin.add_raw(self.render_address(termin['auswahl_terminsort']['lokaltermin']['anschrift'], heading='Terminsort (Lokaltermin)'))
        lokaltermin.add_line('Beschreibung', termin['auswahl_terminsort']['lokaltermin']['beschreibung'])
        if lokaltermin.get_text():
            text.add_raw(lokaltermin.get_text())

        geladene = TextObject()
        for teilnehmer in termin['teilnehmer']:
            geladene.add_raw(self.render_attendees(teilnehmer))
        geladene.add_heading('Geladene')
        if geladene.get_text():
            text.add_raw(geladene.get_text())

        return text.get_text()

    def render_attendees(self, teilnehmer: Dict[str, Any]) -> str:
        """
        Render appointment attendees/summoned parties template.

        Args:
            teilnehmer: Dictionary containing participant/attendee data

        Returns:
            Formatted HTML string containing attendee information
        """
        ladungszusatz = teilnehmer['ladungszusatz']
        geladener = self.akte.rollenverzeichnis.get(str(teilnehmer['ref.rollennummer']))
        datum = teilnehmer['ladungszeit']['ladungsdatum']
        dauer = teilnehmer['ladungszeit']['ladungsdauer']
        ladungsuhrzeit = teilnehmer['ladungszeit']['auswahl_ladungszeit']['ladungsuhrzeit']
        zeitangabe_freitext = teilnehmer['ladungszeit']['auswahl_ladungszeit']['ladungszeitangabe']

        text = TextObject()
        text.add_raw(f"<b>{geladener}</b>")
        if datum:
            text.add_raw(f" am {datum}")
        if ladungsuhrzeit:
            text.add_raw(f" um {ladungsuhrzeit} Uhr")
        if zeitangabe_freitext:
            text.add_raw(f", {zeitangabe_freitext}")
        if dauer:
            text.add_raw(f" für {dauer} h")
        text.add_raw('<br>')
        text.add_line('Ladungszusatz', ladungszusatz)
        text.add_raw('<br>')
        return text.get_text()
