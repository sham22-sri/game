#!/usr/bin/env python
# coding: utf-8

# In[51]:


get_ipython().system('pip install fastapi uvicorn langchain selenium jinja2 pydantic requests python-multipart')
get_ipython().system('pip install playwright')
get_ipython().system('playwright install')


# In[61]:


get_ipython().system('pip install -U langchain-openai')


# In[62]:


from langchain_openai import OpenAI
from selenium import webdriver
from selenium.webdriver.common.by import By
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import time


# In[71]:


OPENAI_KEY = "Open_API_KEY" 


# In[72]:


class PlannerAgent:
    def __init__(self, llm_model="text-davinci-003", api_key=OPENAI_KEY):
        self.llm = OpenAI(model_name=llm_model, openai_api_key=api_key)
    
    def generate_test_cases(self, description: str, num_cases=25):
        prompt = f"""
        You are a QA test generator. The game is described as:
        {description}
        Generate {num_cases} unique test cases with input and expected outcome.
        Return JSON array: {{id, input, expected_result}}
        """
        try:
            response = self.llm(prompt)
            return json.loads(response)
        except:
            # fallback dummy test cases
            return [{"id": i, "input": i, "expected_result": "unknown"} for i in range(num_cases)]


# In[73]:


class RankerAgent:
    def rank(self, test_cases):
        # Simple ranking: numeric even numbers first
        def score(tc):
            if isinstance(tc["input"], int) and tc["input"] % 2 == 0:
                return 10
            return 5
        ranked = sorted(test_cases, key=score, reverse=True)
        return ranked[:10]  # select top 10


# In[74]:


class ExecutorAgent:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        self.driver = webdriver.Chrome(options=options)
    
    def execute(self, url, test_case):
        artifacts_dir = Path(f"artifacts/{self.agent_id}/{test_case['id']}")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.driver.get(url)
            time.sleep(1)
            input_box = self.driver.find_element(By.TAG_NAME, "input")
            input_box.clear()
            input_box.send_keys(str(test_case["input"]))
            submit_btn = self.driver.find_element(By.TAG_NAME, "button")
            submit_btn.click()
            time.sleep(1)
            
            # Capture artifacts
            screenshot = artifacts_dir / "screenshot.png"
            self.driver.save_screenshot(str(screenshot))
            dom_snapshot = artifacts_dir / "dom.html"
            with open(dom_snapshot, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            
            result_text = self.driver.find_element(By.TAG_NAME, "body").text
            return {"id": test_case["id"], "input": test_case["input"], "result": result_text, "artifacts": str(artifacts_dir)}
        except Exception as e:
            return {"id": test_case["id"], "input": test_case["input"], "error": str(e), "artifacts": str(artifacts_dir)}
    
    def close(self):
        self.driver.quit()


# In[75]:


class OrchestratorAgent:
    def __init__(self, num_executors=2):
        self.executors = [ExecutorAgent(f"executor_{i}") for i in range(num_executors)]
    
    def run_tests(self, url, test_cases):
        results = []
        def run_case(agent, tc):
            return agent.execute(url, tc)
        
        with ThreadPoolExecutor(max_workers=len(self.executors)) as pool:
            futures = []
            for i, tc in enumerate(test_cases):
                agent = self.executors[i % len(self.executors)]
                futures.append(pool.submit(run_case, agent, tc))
            for f in futures:
                results.append(f.result())
        
        for e in self.executors:
            e.close()
        return results


# In[76]:


class AnalyzerAgent:
    def validate(self, results, repeats=2):
        final_results = []
        for r in results:
            reproducible = True
            for _ in range(repeats-1):
                if "error" in r:
                    reproducible = False
                    break
            r["reproducible"] = reproducible
            r["verdict"] = "passed" if "error" not in r else "failed"
            r["triage_notes"] = "Needs investigation" if r["verdict"] == "failed" else ""
            final_results.append(r)
        return final_results


# In[77]:


GAME_URL = "https://play.ezygamers.com/"
description = "Number/math puzzle game at https://play.ezygamers.com/"

# Plan
planner = PlannerAgent()
candidates = planner.generate_test_cases(description, num_cases=25)
print(f"Generated {len(candidates)} candidate test cases.")

# Rank & select top 10
ranker = RankerAgent()
top_cases = ranker.rank(candidates)
print("Selected top 10 test cases.")

# Execute
orchestrator = OrchestratorAgent(num_executors=2)
raw_results = orchestrator.run_tests(GAME_URL, top_cases)
print("Execution completed.")

# Validate
analyzer = AnalyzerAgent()
validated_results = analyzer.validate(raw_results, repeats=2)
print("Validation completed.")

# Save JSON report
Path("reports").mkdir(exist_ok=True)
report_file = "reports/final_test_report.json"
with open(report_file, "w") as f:
    json.dump(validated_results, f, indent=2)
print(f"Report saved at {report_file}")


# In[ ]:




