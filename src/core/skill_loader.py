import os
import json
import logging
import importlib.util

logger = logging.getLogger("clawlite.skills")

# Skills directory - separate from workspace for security (read-only in container)
SKILLS_DIR = os.getenv("SKILLS_DIR", "/app/skills")

def discover_and_load_skills():
    active_skills = {}
    
    logger.info(f"Loading skills from: {SKILLS_DIR}")
    
    if not os.path.exists(SKILLS_DIR):
        logger.warning(f"Skills directory not found: {SKILLS_DIR}")
        return active_skills

    for skill_name in os.listdir(SKILLS_DIR):
        skill_path = os.path.join(SKILLS_DIR, skill_name)
        
        if os.path.isdir(skill_path):
            skill_data = {'name': skill_name, 'prompt': '', 'entrypoint': None, 'schema': None}
            
            prompt_file = os.path.join(skill_path, 'prompt.md')
            if os.path.exists(prompt_file):
                with open(prompt_file, 'r') as f:
                    skill_data['prompt'] = f.read()
                    
            schema_file = os.path.join(skill_path, 'schema.json')
            if os.path.exists(schema_file):
                with open(schema_file, 'r') as f:
                    try:
                        skill_data['schema'] = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            main_file = os.path.join(skill_path, 'main.py')
            if os.path.exists(main_file):
                try:
                    spec = importlib.util.spec_from_file_location(f"skill_{skill_name}", main_file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    skill_data['entrypoint'] = module
                    
                    active_skills[skill_name] = skill_data
                    tool_name = skill_data.get('schema', {}).get('tool', skill_name)
                    logger.info(f"✓ Loaded skill: {skill_name} → tool: {tool_name}")
                except Exception as e:
                    logger.error(f"✗ Failed to load skill {skill_name}: {e}")
                
    return active_skills
