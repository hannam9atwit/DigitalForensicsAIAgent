class RefinementEngine:
    """
    Takes the structured narrative and refines it into a more natural,
    human-readable form. This is where an LLM can be plugged in later.
    """

    def refine(self, raw_narrative):
        # For now, we apply deterministic rewriting rules.
        # Later, this can call an LLM for natural language enhancement.

        paragraphs = raw_narrative.split("\n")
        refined = []

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            # Simple heuristics to improve flow
            if p.startswith("##"):
                refined.append(p)  # Keep section headers
                continue

            if p.startswith("- "):
                refined.append(p.replace("- ", "• "))
                continue

            # Improve readability of plain text
            if p.lower().startswith("the forensic analysis"):
                refined.append(
                    "An overview of the system's activity reveals several notable forensic signals. "
                    + p
                )
                continue

            refined.append(p)

        return "\n".join(refined)
