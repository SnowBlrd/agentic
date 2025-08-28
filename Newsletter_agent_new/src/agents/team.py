from agno.team import Team
from agno.models.openai import OpenAIChat

def build_team(collector, curator, writer) -> Team:
    return Team(
        name="Newsletter Team",
        mode="coordinate",
        model=OpenAIChat(id="gpt-4o-mini"),
        members=[collector, curator, writer],
        success_criteria=(
            "Newsletter cohérente: 4–6 sections, 6–12 liens, citations claires, ton homogène."
        ),
        show_members_responses=True,
        show_tool_calls=True,
        markdown=True,
    )