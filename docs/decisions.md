# Decisions

What was chosen, what it cost and when to look again. Entries are appended, not rewritten.

## 1. New settings ship as examples

**Chosen.** Optional group settings and routes are `.yml.example` files. **Why.** A new fleet then gets nothing it did not ask for, and the preflight is not full of placeholders for services nobody runs. **Cost.** A renamed example has to be filled in before it works. **Revisit if** people miss settings because the files are not active.

## 2. Helper scripts are copied from a working fleet, not shared

**Chosen.** The scripts are copied here with fleet names replaced by placeholders. **Why.** A fleet repo has to stand on its own after "Use this template". **Cost.** They can drift from the fleet they came from, which already happened once. **Revisit if** they drift again: moving them into the framework would give them one home.
