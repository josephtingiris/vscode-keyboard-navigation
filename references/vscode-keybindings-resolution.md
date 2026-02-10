# **VS Code Keybinding Resolution: A Technical Reference**

This document explains how Visual Studio Code resolves keybindings when multiple rules, extensions, or `when` clauses compete for the same key.

It is designed to be a definitive quick reference for extension authors and advanced users.

---
# **1. Keybinding Evaluation Model**

When a key is pressed, VS Code evaluates keybinding rules using the following logic:

1. Rules are evaluated **from bottom to top** in the final resolved keybinding list.
2. The first rule whose:
   - `key` matches, and
   - `when` clause evaluates to `true`  
     is selected.
3. Once a matching rule is found, **no further rules are processed**.
4. If the rule has a `command`, that command is executed.

This model is simple but has important implications when multiple rules overlap.

---

# **2. What a `when` Clause Actually Is**

A `when` clause is:

- A **boolean expression**,
- Evaluated against VS Code’s context keys,
- With no concept of priority, specificity, or uniqueness.

VS Code does **not** compare `when` clauses to determine which is "more specific."

They are not ranked, scored, or sorted.

A `when` clause is simply a filter.

If it evaluates to `true`, the rule is eligible.

---

# **3. What Happens When Multiple `when` Clauses Match**

If several rules share the same keybinding and their `when` clauses all evaluate to `true`, VS Code does **not** choose the most specific or complex one.

The winner is always:

### **→ The last matching rule in the evaluation order.**

There is no sub‑sorting of `when` clauses.

---

# **4. The Keybinding Resolution Stack**

VS Code constructs a single ordered list of all keybindings from multiple sources.  
The order (top → bottom) is:

1. **Built‑in defaults**
2. **Built‑in extensions**
3. **Marketplace extensions**  
   Loaded in deterministic extension‑load order
4. **User `keybindings.json`**  
   Always last

Evaluation runs **bottom → top**, so the user’s keybindings always override everything else.

---

# **5. How Extension Keybindings Are Ordered**

When multiple extensions contribute keybindings, VS Code loads them in a deterministic order:

### **Extension load order = extension installation order**

More precisely:

1. Built‑in extensions load first
2. Marketplace extensions load next
3. Within marketplace extensions, the order is stable and based on installation sequence
4. Disabled extensions are ignored

This means:

### **→ If two extensions define the same keybinding, the extension loaded later wins**

(unless the user overrides it).

There is no priority system for extensions beyond load order.

---

# **6. Example: Competing Extension Keybindings**

Suppose:

- Extension A was installed first
- Extension B was installed later

Both define:

```json
{
  "key": "ctrl+k",
  "command": "doSomething"
}
```

If both `when` clauses evaluate to `true`:

### **→ Extension B wins**

because it appears lower in the resolved keybinding list.

---

# **7. Example: Multiple Rules With Matching `when` Clauses**

```json
{
  "key": "ctrl+k",
  "command": "doA",
  "when": "editorTextFocus"
},
{
  "key": "ctrl+k",
  "command": "doB",
  "when": "editorTextFocus && !editorReadonly"
},
{
  "key": "ctrl+k",
  "command": "doC",
  "when": "editorTextFocus"
}
```

If all three `when` clauses evaluate to `true`:

### **→ `doC` wins**

because it is the last rule in the list.

VS Code does not consider that `doB` has a “more specific” `when` clause.

---

# **8. Practical Guidance for Extension Authors**

To ensure predictable behavior:

### **Put your most specific rule last.**

Fallback rules should appear above it.

### **Use `when` clauses to narrow scope, not to establish priority.**

Priority comes only from ordering.

### **Expect users to override you.**

User keybindings always win.

### **Avoid collisions with popular extensions.**

If you must bind to common keys, provide configuration options.

---

# **9. Mental Model**

Think of VS Code’s keybinding system as a **stack**:

```
Evaluation Order: Bottom → Top (First matching rule wins)

┌───────────────────────────────────────────────┐
│                Built‑in Defaults              │
│      (VS Code’s internal default bindings)    │
└───────────────────────────────────────────────┘
                     ▲
                     │
┌───────────────────────────────────────────────┐
│             Built‑in Extensions               │
│   (Git, Markdown, TypeScript, etc.)           │
└───────────────────────────────────────────────┘
                     ▲
                     │
┌───────────────────────────────────────────────┐
│          Marketplace Extensions               │
│ (Loaded in deterministic installation order)  │
└───────────────────────────────────────────────┘
                     ▲
                     │
┌───────────────────────────────────────────────┐
│              User Keybindings                 │
│  (keybindings.json — bottom up, always wins)  │
└───────────────────────────────────────────────┘
```

When a key is pressed:

- VS Code walks **bottom → up**
- The first rule whose key + `when` clause match is executed
- No further rules are considered

There is no specificity scoring, no tie‑breaking logic, and no sub‑sorting of `when` clauses.

---

# **10. Flowchart TD**

```
A[Key Pressed] --> B{Does key match any rule?}

B -->|No| Z[No command executed]
B -->|Yes| C[Collect all matching keybinding rules]

C --> D[Sort rules by evaluation order:<br/>1. User keybindings.json<br/>2. Marketplace extensions<br/>3. Built‑in extensions<br/>4. Built‑in defaults]

D --> E[Evaluate rules bottom → top]

E --> F{Does rule's<br/>when clause evaluate to true?}

F -->|No| E
F -->|Yes| G[Select this rule]

G --> H[Execute command]
```

# **11. Summary**

- `when` clauses are boolean filters, not priority indicators.
- The last matching rule wins.
- User keybindings override everything.
- Extension keybindings are ordered by installation order.
- There is no “most specific” rule — only the last eligible one.