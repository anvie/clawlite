"""
Weather skill for ClawLite.

This is the main entry point. The execute() function is called
when the LLM invokes this skill's tool.
"""


def execute(args: dict) -> str:
    """
    Execute the Weather skill.
    
    Args:
        args: Dictionary of arguments as defined in schema.json
        
    Returns:
        String result to show to user
    """
    # TODO: Implement your skill logic here
    example_param = args.get("example_param", "default")
    
    return f"Weather executed with: {{example_param}}"
