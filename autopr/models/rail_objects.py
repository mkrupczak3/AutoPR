import json
from typing import List, ClassVar, Optional, Union
from typing_extensions import TypeAlias

import pydantic

from autopr.models.artifacts import DiffStr


class RailObject(pydantic.BaseModel):
    """
    A RailObject is a pydantic model that represents the output of a guardrails call.
    See PromptRail and RailService, and [Guardrails docs](https://docs.guardrails.io/) for more information.

    To define your own RailObject:
    - write an XML string compatible with the guardrails XML spec in the `output_spec` class variable
    - define your parameters as pydantic instance attributes
    """

    output_spec: ClassVar[str]

    @classmethod
    def get_rail_spec(cls):
        """
        Get the XML spec template used to define the guardrails output.
        Should include a `{{raw_document}}` in the prompt section,
        which will be replaced by the input prompt/two-step LLM output.
        """
        return f"""
<rail version="0.1">
<output>
{cls.output_spec}
</output>
<prompt>
```
{{{{raw_document}}}}
```

@complete_json_suffix_v2
</prompt>
</rail>
"""


class FileHunk(RailObject):
    output_spec = """<string
    name="filepath"
    description="The path to the file we are looking at."
    format="filepath"
    on-fail="fix"
/>
<integer
    name="start_line"
    description="The line number of the first line of the hunk."
    format="positive"
    required="false"
    on-fail="noop"
/>
<integer
    name="end_line"
    description="The line number of the last line of the hunk."
    format="positive"
    required="false"
    on-fail="noop"
/>"""

    filepath: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None

    def __str__(self):
        s = self.filepath
        if self.start_line is not None:
            s += f":L{self.start_line}"
            if self.end_line is not None:
                s += f"-L{self.end_line}"
        return s


class CommitPlan(RailObject):
    output_spec = f"""<string
    name="commit_message"
    description="The commit message, concisely describing the changes made."
    length="1 100"
    on-fail="noop"
/>
<list
    name="relevant_file_hunks"
    description="The files we should be looking at while writing this commit. Include files that whose contents will be called by the code in this commit, and files that will be changed by this commit."
>
<object>
{FileHunk.output_spec}
</object>
</list>
<string
    name="commit_changes_description"
    description="A description of the changes made in this commit, in the form of a list of bullet points."
    required="true"
    length="1 1000"
/>"""

    commit_message: str
    relevant_file_hunks: List[FileHunk] = pydantic.Field(default_factory=list)
    commit_changes_description: str = ""

    def __str__(self):
        return self.commit_message + '\n\n' + self.commit_changes_description


class PullRequestDescription(RailObject):
    output_spec = f"""<string 
    name="title" 
    description="The title of the pull request."
/>
<string 
    name="body" 
    description="The body of the pull request."
/>
<list 
    name="commits"
    on-fail="reask"
    description="The commits that will be made in this pull request. Commits must change the code in the repository, and must not be empty."
>
<object>
{CommitPlan.output_spec}
</object>
</list>"""

    title: str
    body: str
    commits: list[CommitPlan]

    def __str__(self):
        pr_text_description = f"Title: {self.title}\n\n{self.body}\n\n"
        for i, commit_plan in enumerate(self.commits):
            prefix = f" {' ' * len(str(i + 1))}  "
            changes_prefix = f"\n{prefix}  "
            pr_text_description += (
                f"{str(i + 1)}. Commit: {commit_plan.commit_message}\n"
                f"{prefix}Files: "
                f"{', '.join([str(fh) for fh in commit_plan.relevant_file_hunks])}\n"
                f"{prefix}Changes:"
                f"{changes_prefix}{changes_prefix.join(commit_plan.commit_changes_description.splitlines())}\n"
            )
        return pr_text_description
