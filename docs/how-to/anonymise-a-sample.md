# Anonymise a sample

A file from some estimating package is read incorrectly, and you want to show the problem. Real CUF
files contain client names and addresses and prices that are often confidential bids, so they must
never be posted in an issue, a pull request or an AI chat. This page shows how to make a small
file that shows the problem without any real data.

## 1. Start from the smallest file that shows the problem

The best sample is not a real file at all but a few hand-written lines. A complete CUF-XML file
can be this small:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CUF AANMAAKDATUMTIJD="2026-01-01T12:00:00">
  <PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"
                   PROJECTNAAM="Voorbeeld"/>
  <BEGROTING UREN="0" LOONKOSTEN="0" MATERIAALKOSTEN="500" MATERIEELKOSTEN="0"
             ONDERAANNEMING="0" OVERIGE_KOSTEN="0">
    <BUNDELING CODE="1" OMSCHRIJVING="Metselwerk">
      <BEGROTINGSREGEL CODE="1.1" OMSCHRIJVING="metselwerk" HOEVEELHEID="10"
                       HOEVEELHEID_EENHEID="m2" MATERIAALPRIJS="50" BTW="21"/>
    </BUNDELING>
  </BEGROTING>
  <STAARTGEGEVENS AANNEEMSOM="500"/>
</CUF>
```

Add only what reproduces the problem: the odd attribute, the unusual nesting, the date format.

## 2. If you must start from a real file

1. **Cut** everything that is not needed: keep one bundle and one or two lines that show the
   problem, plus the `PROJECTGEGEVENS` element and the XML declaration.
2. **Replace** every name, address, project name and number, description, code and comment with
   fictitious values (`Voorbeeld`, `regel 1`, `A1`).
3. **Change the amounts**, keeping only what the problem needs (for example the number of
   decimals, a zero, or that a total does not add up).
4. **Keep byte for byte** what is often the bug: the XML declaration and its encoding, a byte-order
   mark, the line endings, the namespace declarations and any vendor attributes. Edit the file with
   an editor that preserves the encoding (Windows-1252 files must stay Windows-1252).

## 3. Check the result

```console
pycuf validate sample.xml
```

The sample should still show the problem (the same finding codes, or the same wrong result), and
it should contain nothing you would not post on a public website. When in doubt, leave it out.

## 4. Share it

Open a [file compatibility report](https://github.com/SpireflyHQ/pycuf/issues/new?template=file_compatibility.yml)
with the exporting software and version, the finding codes, and the sample pasted as text. If you
open a pull request that adds the sample to the tests, confirm in it that the sample contains no
real data and may be published under the MIT license.
