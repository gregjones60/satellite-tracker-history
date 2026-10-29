"""User-facing summaries of completed archive imports."""
def import_message(result):
    lines = [f"**{result['added']:,} locations added**",
             f"Duplicates ignored: {result['duplicates']:,}",
             f"Invalid or unnamed records skipped: {result['skipped']:,}",
             f"Source records: {result['total']:,}"]
    if result['start_time'] is not None:
        lines.append(f"Valid source date range (UTC): {result['start_time']} to {result['end_time']}")
    lines.append(f"Destination feeds: {len(result['destinations'])}")
    lines.append('To view older history, refresh the map and select the matching year or dates. The default view shows only recent history.')
    return '\n\n'.join(lines)
