
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def get_chrome_options():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    
    # Disable images/CSS for speed
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
    }
    options.add_experimental_option("prefs", prefs)
    
    return options

def scrape_single_product(link, options):
    """Scrape a single product with its own driver instance"""
    driver = webdriver.Chrome(options=options)
    product_data = {}
    
    try:
        driver.get(link)
        wait = WebDriverWait(driver, 10)
        
        # Get product title
        product_title = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "span.a-size-large.product-title-word-break")
        )).text
        
        product_data = {}
        
        # Get table 1 specs
        try:
            table1 = driver.find_element(By.ID, "productDetails_techSpec_section_1")
            rows1 = table1.find_elements(By.TAG_NAME, "tr")
            for row in rows1:
                header = row.find_element(By.TAG_NAME, 'th').text
                data = row.find_element(By.TAG_NAME, 'td').text
                product_data[header] = data
        except:
            pass
        
        # Get table 2 specs
        try:
            table2 = driver.find_element(By.ID, "productDetails_techSpec_section_2")
            rows2 = table2.find_elements(By.TAG_NAME, "tr")
            for row in rows2:
                header = row.find_element(By.TAG_NAME, 'th').text
                data = row.find_element(By.TAG_NAME, 'td').text
                product_data[header] = data
        except:
            pass
        
        # Add product link
        product_data["product_link"] = link
        
        # Get price
        try:
            sign = driver.find_element(By.CSS_SELECTOR, "span.a-price-symbol").text
            price = driver.find_element(By.CSS_SELECTOR, "span.a-price-whole").text
            product_data["price"] = sign + " " + price
        except:
            product_data["price"] = "N/A"
        
        return product_title, product_data
        
    except Exception as e:
        print(f"Error scraping {link}: {e}")
        return None, None
    finally:
        driver.quit()


def amazon_searcher(queries, max_workers=5):
    """
    Scrape Amazon products in parallel
    
    Args:
        queries: List of search queries
        max_workers: Number of parallel browser instances (default: 5)
    """
    specs = {}
    options = get_chrome_options()
    
    # Main driver just for collecting product links
    driver = webdriver.Chrome(options=options)
    
    try:
        for query in queries:
            print(f"Searching for: {query}")
            product_links = []
            page = 1
            link = f'https://www.amazon.com/s?k={query}&page={page}'
            driver.get(link)

            # Collect product links (up to 50)
            while len(product_links) < 50:
                try:
                    products = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"][data-component-type="s-search-result"]')
                    
                    for product in products:
                        try:
                            link_element = product.find_element(By.TAG_NAME, "a")
                            link_url = link_element.get_attribute("href")
                            if link_url:  # Make sure link is not None
                                product_links.append(link_url)
                        except:
                            continue

                    print(f"Collected {len(product_links)} product links so far...")

                    if len(product_links) >= 50:
                        break
                    
                    # Go to next page
                    page += 1
                    link = f'https://www.amazon.com/s?k={query}&page={page}'
                    driver.get(link)
                    
                except Exception as e:
                    print(f"Error collecting links on page {page}: {e}")
                    break
            
            # Limit to 50 products
            product_links = product_links[:50]
            print(f"Starting parallel scraping of {len(product_links)} products...")
            
            # Scrape products in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all scraping tasks
                future_to_link = {
                    executor.submit(scrape_single_product, link, options): link 
                    for link in product_links
                }
                
                # Process completed tasks as they finish
                completed = 0
                for future in as_completed(future_to_link):
                    completed += 1
                    try:
                        product_title, product_data = future.result()
                        if product_title and product_data:
                            specs[product_title] = product_data
                            print(f"✓ Scraped {completed}/{len(product_links)}: {product_title[:50]}...")
                        else:
                            print(f"✗ Failed {completed}/{len(product_links)}")
                    except Exception as e:
                        print(f"✗ Error processing result {completed}/{len(product_links)}: {e}")
            
            print(f"Completed scraping for query: {query}")
            print(f"Total products scraped: {len(specs)}\n")
    
    finally:
        driver.quit()
    
    return specs

# Usage
# queries = ["laptop for gaming"]
# start = time.time()
# results = amazon_searcher(queries, max_workers=5)
# end = time.time() - start
# print(f"\nTotal products scraped: {len(results)}\ntime_taken: {end}")

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/amazon_scraper")
def amazon_scraper(query:str):
    try:
        queries = [query]
        start = time.time()
        results = amazon_searcher(queries, max_workers=1)
        end = time.time() - start
        return JSONResponse(content={
                "success": True,
                "query": query,
                "total_products": len(results),
                "time_taken_seconds": round(end, 2),
                "products": results  # Include the actual data
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")