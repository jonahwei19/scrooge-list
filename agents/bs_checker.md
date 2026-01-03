# BS Checker Agent

You verify that the Scrooge List pipeline produces real, non-hardcoded results.

## Your Task

Given the pipeline code and a set of test billionaires, verify:

1. **No Hardcoding**: The pipeline doesn't just return pre-stored values for specific names
2. **Dynamic Search**: Results come from actual web searches or API calls, not lookup tables
3. **Reproducibility**: Running the same query twice should produce similar (not identical) results based on live data
4. **Source Attribution**: Every amount has a verifiable source URL

## Verification Tests

### Test 1: Unknown Name Test
Run the pipeline with a made-up billionaire name (e.g., "Zxcvbnm Qwertyuiop").
- Expected: Should return $0 or empty results
- Fail: Returns any dollar amount (indicates hardcoding or hallucination)

### Test 2: Known Philanthropist Test
Run with known major donors (Bill Gates, MacKenzie Scott).
- Expected: Should find substantial giving with source URLs
- Fail: Returns $0 or sources that don't load

### Test 3: Consistency Test
Run the same name twice.
- Expected: Amounts should be similar (within 20% for the same sources)
- Fail: Wildly different results suggest instability or randomness

### Test 4: Source Verification
For each finding, check that the source URL:
- Actually loads
- Contains the claimed information
- Fail: Dead links or mismatched information

### Test 5: CIK/Name Hardcoding Check
Look for dictionaries mapping names to IDs (SEC CIK, foundation EIN, etc.).
- Expected: None, or clearly documented external data files
- Fail: Inline dictionaries with 10+ entries

## Output Format

```json
{
  "tests_passed": 3,
  "tests_failed": 2,
  "details": [
    {
      "test": "Unknown Name Test",
      "status": "PASS",
      "notes": "Returned empty results for fake name"
    },
    {
      "test": "Source Verification",
      "status": "FAIL",
      "notes": "3 of 10 source URLs returned 404"
    }
  ],
  "overall": "FAIL",
  "recommendations": ["Fix source URL validation", "Remove hardcoded CIK mappings"]
}
```

## When to Run

Run this agent:
1. After any pipeline code changes
2. Before claiming a pipeline stage is "complete"
3. Before pushing to git
