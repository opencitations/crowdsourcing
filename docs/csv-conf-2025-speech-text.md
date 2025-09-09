# CSV Conf 2025: Speech Text

## Slide 1: Title Slide

"Raise your hand if you've ever published a paper." 

[Wait for response] 

"Keep it up if that paper cited research from a journal outside the United States or Europe." 

[Pause] 

"Now keep it up if you can actually find those citations in Web of Science or Scopus today." 

[Watch hands disappear]

---

## Slide 2: The Invisible Crisis

"What you just saw is the invisible knowledge crisis. There are 52,000 active journals using Open Journal Systems - OJS - worldwide. OJS is an open-source platform that universities and research institutions use to publish their academic journals. It's the backbone of scholarly publishing in much of the world.

A 2022 study found that 79.9 percent of these OJS journals are in the Global South. Yet 98.8 percent are invisible to Web of Science, and 94.3 percent don't appear in Scopus."

---

## Slide 3: Not Predatory, Just Invisible

"Before you think these are predatory journals - only 1 percent appear in Cabell's Predatory Reports, and 1.4 percent made Beall's list. These lists have their own transparency issues, but the data indicates these are mostly legitimate journals publishing real science. We're not talking about bad science. We're talking about invisible science."

---

## Slide 4: OpenCitations Today

"My name is Arcangelo Massari, and I'm a developer with OpenCitations. Since 2010, OpenCitations has been building open citation infrastructure. We have 2.2 billion open citations and 124 million bibliographic entities. 

I'll show you how we're approaching this problem. We're working to make 52,000 journal editors into citation contributors using their existing workflow. We built transparency like Wikipedia but with access controls.

We don't have a technology problem. We have a bridge problem."

---

## Slide 5: The Bridge Problem

"Here's what invisible means. A researcher in Ghana publishes work on climate adaptation. A scientist in Brazil cites it. That citation exists, but it's trapped in a PDF that Web of Science will never crawl.

Multiply this by millions of papers, and you get citation networks with massive holes. Like having a map of the internet that only shows dot-com and dot-org, ignoring everything else.

When citations disappear, research impact becomes invisible. Careers suffer. Entire fields get orphaned from the global conversation. We're losing the connections that make knowledge cumulative."

---

## Slide 6: The Partnership

"OpenCitations partnered with PKP, the organization behind Open Journal Systems, and TIB, Germany's National Library of Science and Technology. We're extending OJS with a citation submission workflow.

What if we could make this knowledge visible through the workflow editors already use?"

---

## Slide 7: The Simple Workflow

"The workflow is simple. Editors copy and paste references into a field in the OJS dashboard. The system parses these to extract metadata. Editors can correct any parsing errors before submission."

---

## Slide 8: Technical Implementation

"Citations become CSV files: one for bibliographic metadata with columns like 'id', 'title', 'author', 'pub_date', 'venue' - another for citation relationships with 'citing_id' and 'cited_id'. They go to GitHub as structured issues with titles like 'deposit umanisticadigitale.unibo.it doi:10.6092/issn.2532-8816/21218', containing both CSVs."

---

## Slide 9: Validation Pipeline

"The validation pipeline has three stages. First, structural validation: the title must match 'deposit domain identifier', the body must contain two CSVs separated by '===###===@@@===', and both CSVs must have proper column headers and format.

Second, semantic validation: we verify all identifiers using external APIs - DOIs through Crossref and PMIDs through PubMed. We validate that bibliographic resource types match their fields, that authors and venues have proper identifiers, and that all metadata is semantically consistent.

Third, closure validation: every citation must have corresponding metadata entries for both citing and cited works. This prevents orphaned citations and ensures data completeness.

Failed validations generate detailed HTML reports showing specific errors. Unauthorized users get 'rejected'. Valid data gets 'to be processed', then 'done' after monthly ingestion to OpenCitations Index and Meta."

---

## Slide 10: Scope and limitations

One limitation: this processes new publications, not retrospective content. When a journal adopts the plugin, it contributes citations going forward. Extracting from archived articles is a different challenge for future work.

But if we open this to everyone, we create a new problem."

---

## Slide 11: Trust Through Transparency

"Trust requires preventing manipulation and ensuring provenance. Citation manipulation can inflate careers and distort science. But locking down kills collaboration.

We combine controlled access with transparency. Unlike Beall's List - where one person makes opaque decisions - our safe list has a board with PKP and OpenCitations members. They publish criteria for inclusion and exclusion. Every decision is documented and public. No black boxes, no individual gatekeepers. This prevents gaming while avoiding arbitrary exclusion."

---

## Slide 12: Infrastructure Independence

"Every contribution goes through GitHub - visible, documented, reversible. Data gets archived in Zenodo. We're not dependent on commercial platforms that could change policies. The data lives on stable, open European infrastructure."

---

## Slide 13: Global Impact

"Result: quality control that scales to 41,500 Global South journals with complete provenance.

Trust through transparency."

---

## Slide 14: Use OpenCitations Today

"What this means for you: those 52,000 OJS journals won't publish in isolation anymore. Their citations become part of your datasets.

OpenCitations already has 2.2 billion citation relationships as open data - no login, no paywall, CC0. Download dumps, use REST APIs, or SPARQL. With crowdsourcing, we'll add millions more from the Global South. We're democratizing the citation graph."

---

## Slide 15: Join Us

"Use OpenCitations data in your projects. Build visualizations of citation patterns across continents. Create analyses including Global South research. Integrate our APIs. Show what's possible with open citation data.

The infrastructure is in development. The partnerships are in place. Join us."

---

## Slide 16: Thank You & Contact

"Thank you."

[Display contact information and QR codes on screen]