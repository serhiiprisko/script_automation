
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import requests
import json
import re
import random
import sys
import time
import configparser

from twocaptcha import TwoCaptcha

from shopware_client import rest
from prestashop_client import presta

is_upload_to_shopware = True # else upload to prestashop
str_keyword = ''
is_search_by_keyword = -1 # 0: scrape by keyword, 1: scrape by url
max_products = -1
max_images = -1
min_price_reduction = -1
max_price_reduction = -1
min_price_filter = -1
max_price_filter = -1
captcha_api_key = ''
is_otto = False
is_mediamarkt = False
is_fahrrad = False
str_urls = None
is_round00 = True
title_search = False
single_url = ''

is_round = True
prestashop = None
shopware = None
prestashop_categories = json.loads('{}')
shopware_categories = json.loads('{}')
prestashop_manufacturers = json.loads('[]')
uploaded_count = 0
mediamarkt_driver = None

def write_to_file(path, soup):
	f = open(path, "w", encoding="utf-8")
	f.write(str(soup))
	f.close()

def read_from_file(path):
	f = open(path, "r", encoding="utf-8")
	return BeautifulSoup(f.read(), 'lxml')

def pprint(str):
	sys.stdout.write(str)
	sys.stdout.flush()

def exit_me():
	if mediamarkt_driver != None:
		mediamarkt_driver.close()
	time.sleep(1)
	pprint('Finished scraping\n')
	exit()
	
def check_categories_shopware(categories):
	global shopware_categories
	
	parent_id = 1
	
	for category in categories:
		cat_name = str(category)
		cat_id = -1
		for a_cat in shopware_categories:
			if a_cat['name'] == cat_name and a_cat['parentId'] == parent_id:
				cat_id = int(a_cat['id'])
		if cat_id == -1: # create new category
			cat_id = shopware.create_category(cat_name, parent_id)
			shopware_categories = shopware.get_categories()
		parent_id = cat_id
	
	return parent_id

def upload_product_shopware(name, description, price, images, number, articleNr, supplier, eans, categories, variants):
	category_id = check_categories_shopware(categories)
	
	#price = price * 1.19
	#price = round(price)
	if is_round00 == False:
		price = price - 0.01
	if price < 0:
		price = 0
	
	index = 0
	for a_variant in variants:
		a_number = articleNr + str(index)
		a_name = name
		if a_variant != '':
			a_name = name + ' - ' + a_variant
		a_ean = eans[index]
		
		index = index + 1
		
		data = {
			'name': a_name,
			'descriptionLong': description,
			'active': 1,
			'tax': 19,
			'mainDetail': {
				'number': a_number,
				'inStock': 9999,
				'active': 1,
				'prices': [
					{'price': price},
				],
				'ean': a_ean,
			},
			'images': images,
			'categories': [
				{'id':category_id},
			],
			'supplier': supplier,
		}

		try:
			a_article = shopware.get_article(a_number, True)
			#pprint('>>>> Already exists.\n')
			# update article
			# shopware.put('/articles/%s' % a_article['id'], data)
		except:
			# create article
			pprint('>>>> Adding product...\n')
			try:
				shopware.post('/articles', data)
			except:
				return


def get_categories_prestashop():
	global prestashop_categories
	prestashop_categories = json.loads('[]')
	
	j_schema = json.loads(prestashop.getJSON('categories/?output_format=JSON&display=full'))
	j_categories = j_schema["categories"]
	for j_category in j_categories:
		j_obj = json.loads('{}')
		j_obj['id'] = j_category['id']
		j_obj['parentId'] = int(j_category['id_parent'])
		j_obj['name'] = j_category['name']
		prestashop_categories.append(j_obj)

def create_category_prestashop(name, parentId):
	blank_schema = prestashop.get('categories?schema=blank')
	j_schema = json.loads(json.dumps(blank_schema))
	j_category = j_schema["category"]
	j_category["id_parent"] = str(parentId);
	j_category["name"]["language"]["#text"] = name
	j_category["link_rewrite"]["language"]["#text"] = name
	j_category["active"] = "1"
	
	result = prestashop.add('categories', j_schema)
	j_schema = json.loads(json.dumps(result))
	return int(j_schema["category"]["id"])

def check_categories_prestashop(categories):
	parent_id = 2
	
	index = 0
	
	for category in categories:
		index = index + 1
		if index == 1:
			continue
		
		cat_name = str(category)
		cat_id = -1
		for a_cat in prestashop_categories:
			if a_cat['name'] == cat_name and a_cat['parentId'] == parent_id:
				cat_id = a_cat['id']
		if cat_id == -1: # create new category
			cat_id = create_category_prestashop(cat_name, parent_id)
			get_categories_prestashop()
		parent_id = cat_id
	
	return parent_id
	
def get_manufacturers_prestashop():
	global prestashop_manufacturers
	prestashop_manufacturers = json.loads('[]')
	
	j_schema = json.loads(prestashop.getJSON('manufacturers/?output_format=JSON&display=full'))
	if len(j_schema) == 0:
		return
	j_manufacturers = j_schema["manufacturers"]
	for j_manufacturer in j_manufacturers:
		j_obj = json.loads('{}')
		j_obj['id'] = j_manufacturer['id']
		j_obj['name'] = j_manufacturer['name']
		prestashop_manufacturers.append(j_obj)

def create_manufacturer_prestashop(name):
	blank_schema = prestashop.get('manufacturers?schema=blank')
	j_schema = json.loads(json.dumps(blank_schema))
	j_manufacturer = j_schema["manufacturer"]
	
	j_manufacturer["name"] = name
	j_manufacturer["active"] = "1"
	
	result = prestashop.add('manufacturers', j_schema)
	j_schema = json.loads(json.dumps(result))
	return int(j_schema["manufacturer"]["id"])

def check_manufacturer_prestashop(manufacturer):
	manu_id = -1
	for a_manu in prestashop_manufacturers:
		if a_manu['name'] == manufacturer:
			manu_id = int(a_manu['id'])
			break
	if manu_id == -1: # create new category
		manu_id = create_manufacturer_prestashop(manufacturer)
		get_manufacturers_prestashop()
	
	return manu_id

def download_img_to_temp(url):
	req = requests.get(url, stream=True, headers={'User-agent': 'Mozilla/5.0'})
	req.raise_for_status()
	with open('__temp.jpg', 'wb') as fd:
		for chunk in req.iter_content(chunk_size=50000):
			fd.write(chunk)
		
def upload_product_prestashop(name, description, price, images, number, articleNr, supplier, eans, categories, variants):
	#price = price * 1.19
	#price = round(price)
	if is_round00 == True:
		price = price / 1.19
	else:
		price = (price - 0.01) / 1.19
	price = round(price * 1000000)
	price = price / 1000000
	if price < 0:
		price = 0
	name = name[0:120]
		
	category_id = check_categories_prestashop(categories)
	manufacturer_id = check_manufacturer_prestashop(supplier)
	
	index = 0
	for a_variant in variants:
		a_name = name
		if a_variant != '':
			a_name = name + ' - ' + a_variant
		a_ean = eans[index]
		
		index = index + 1
		
		j_exists = json.loads(prestashop.getJSON('products/?display=full&output_format=JSON&filter[ean13]='+a_ean))
		if (len(j_exists) > 0):
			continue
		
		blank_schema = prestashop.get('products?schema=blank')
		j_schema = json.loads(json.dumps(blank_schema))
		j_product = j_schema["product"]
		j_product["id_category_default"] = json.loads('{}')
		j_product["id_category_default"]["#text"] = str(category_id)
		j_product["id_manufacturer"] = json.loads('{}')
		j_product["id_manufacturer"]["#text"] = str(manufacturer_id)
		j_product["associations"]["categories"]["category"]["id"] = str(category_id)
		j_product["name"]["language"]["#text"] = a_name
		j_product["description"]["language"]["#text"] = description
		j_product["price"] = str(price)
		j_product["visibility"] = "both"
		j_product["available_for_order"] = "1"
		j_product["show_price"] = "1"
		j_product["reference"] = articleNr
		j_product["ean13"] = a_ean
		j_product["active"] = "1"
		j_product["state"] = "1"
		j_product["id_tax_rules_group"] = json.loads('{}')
		j_product["id_tax_rules_group"]["#text"] = "1"
		
		pprint('>>>> Adding product...\n')
		result = prestashop.add('products', j_schema)
		j_schema = json.loads(json.dumps(result))
		product_id = j_schema["product"]["id"]
		stock_id = j_schema["product"]["associations"]["stock_availables"]["stock_available"]["id"]
		
		pprint('>>>> Updating stocks...\n')
		j_stock = json.loads(json.dumps(prestashop.get('stock_availables/' + stock_id)))
		j_stock['stock_available']['quantity'] = 9999;
		prestashop.edit('stock_availables/' + stock_id, j_stock)
		
		pprint('>>>> Uploading images...\n')
		for j_image in images:
			try:
				download_img_to_temp(j_image['link'])
				prestashop.add_image("products/" + product_id, "__temp.jpg")
			except:
				continue

def upload_product(name, description, price, images, number, articleNr, supplier, ean, categories, variants):
	global uploaded_count
	
	description = description.replace('otto', '')
	description = description.replace('Otto', '')
	description = description.replace('MediaMarkt', '')
	description = description.replace('mediamarkt', '')
	
	if title_search == True and is_search_by_keyword == 0:
		if str_keyword.lower() not in name.lower():
			pprint('>>> Title does not match.\n')
			return
	
	if is_upload_to_shopware:
		upload_product_shopware(name, description, price, images, number, articleNr, supplier, ean, categories, variants)
	else:
		upload_product_prestashop(name, description, price, images, number, articleNr, supplier, ean, categories, variants)
		
	pprint('>>> Done.\n')
	uploaded_count = uploaded_count + 1
	if uploaded_count >= max_products:
		exit_me()

def wait_for_lazyload(driver): # unworking
	while True:
		check_height = driver.execute_script("return document.body.scrollHeight;")
		driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
		time.sleep(3)
		if (check_height == driver.execute_script("return document.body.scrollHeight;")):
			break
	
def get_content_url(url):
	options = webdriver.ChromeOptions()
	options.add_experimental_option('excludeSwitches', ['enable-logging'])
	driver = webdriver.Chrome(executable_path=r"py/chromedriver.exe", options=options)
	driver.set_window_position(-10000, 0)
	driver.set_window_size(10, 10)
	driver.set_page_load_timeout(300)
	try:
		driver.get(url)
		#wait_for_lazyload(driver)
		content = driver.page_source
		soup = BeautifulSoup(content, 'lxml')
	except:
		soup = ''
	driver.close()
	return soup

# otto.de functions
"""
def get_pages_count_otto(ul):
	total_pages = '1'
	if ul != None:
		for a_li in ul.findAll('li'):
			if a_li.get('id') == 'san_pagingBottomNext':
				break
			if a_li.get('id') == 'san_pagingDots':
				continue
			if a_li.get('id') == 'san_pagingBottomPrev':
				continue
			button = a_li.find('button')
			total_pages = button.text
"""
	
def get_next_page_otto(ul):
	data_page = ''
	if ul != None:
		_break = False
		for a_li in ul.findAll('li'):
			if _break == True:
				data_page = str(a_li.find('button').get('data-page'))
				break;
			if a_li.get('id') == 'san_pagingCurrentPage':
				_break = True
	if data_page == '':
		return ''
	json_data = json.loads(data_page)
	return "l=" + json_data["l"] + "&o=" + json_data["o"]

def patch_image_src_otto(src):
	src = src.split('?')[0]
	return json.loads('{\"link\":\"' + src + '\"}')

def get_a_product_otto(url):
	product_name = ''
	product_price = 0.0
	product_description = ''
	product_number = ''
	product_articleNr = ''
	product_images = json.loads('[]')
	product_manufacturer = ''
	product_ean = json.loads('[]')
	product_categories = json.loads('[]')
	product_variant = json.loads('[]')
	product_variant.append('')
	
	pprint('>>> Uploading product \"' + url + '\"\n')
	soup = get_content_url(url)
	if soup == '':
		return
	
	div_name = soup.find('h1', {"class":"js_shortInfo__variationName prd_shortInfo__variationName"})
	product_name = div_name.text
	product_manufacturer = product_name.split(' ')[0]
	
	div_articleNr = soup.find(id='articleNr')
	if div_articleNr != None:
		product_articleNr = div_articleNr.find('span').text
		
	div_json = soup.find(id='productDataJson')
	try:
		jobj_product = json.loads(str(div_json.contents[0]))
		variantion_id = jobj_product['sortedVariationIds'][0]
		
		jobj_product = jobj_product['variations'][variantion_id]
		product_ean.append(jobj_product['ean'])
		
		image_count = 0
		for a_json_image in jobj_product['images']:
			if (image_count == max_images):
				break
			product_images.append(patch_image_src_otto('https://i.otto.de/i/otto/' + a_json_image['id']))
			image_count = image_count + 1
	except:
		pprint('>>>> EAN parse error\n')
		return
		
	div_categories = soup.find('ul', {"class":"nav_grimm-breadcrumb"})
	if div_categories == None:
		div_categories = soup.find('ul', {"class":"nav_breadcrumb"})
	if div_categories != None:
		for a_li_category in div_categories.findAll('li'):
			if 'nav_grimm-breadcrumb__ellipsis-item' in str(a_li_category.get('class')):
				continue
			product_categories.append(a_li_category.find('a').text)
	
	div_price = soup.find('div', {"class":"prd_price__main js_prd_price__main"})
	if div_price != None:
		product_price = float(div_price.find('span').find('span').get('content'))
		if (product_price > max_price_filter):
			pprint('>>>> Skipped by price filter.\n')
			return
		if (product_price < min_price_filter):
			pprint('>>>> Skipped by price filter.\n')
			return
		product_price = (100 - random.randint(min_price_reduction, max_price_reduction)) * product_price / 100
		if is_round == True:
			product_price = round(product_price)
	
	div_section = soup.find(id='description')
	if div_section != None:
		for a_image in div_section.findAll('img'):
			a_image_src = "https://www.otto.de" + a_image.get('src')
			a_image['src'] = a_image_src
		for a_script in div_section.findAll('script'):
			a_script.decompose()
		div_moreBox_content = div_section.find('div', {"class":"prd_moreBox__content js_prd_moreBox__content"})
		if div_moreBox_content == None:
			div_moreBox_content = div_section.find('div', {"class":"prd_moreBox__content pl_copy100 js_prd_moreBox__content"})
		if div_moreBox_content != None:
			div_section = div_moreBox_content
		product_description = str(div_section.decode_contents())
	
	div_details = soup.select('div[class*="prd_details"]')
	if len(div_details) != 0:
		div_details = div_details[0]
		for a_table_detail in div_details.findAll('table'):
			a_table_detail['padding'] = '8px 8px 6px'
			a_table_detail['style'] = 'margin-top: 16px; width: 100%'
			a_caption = a_table_detail.find('caption')
			if a_caption != None:
				a_caption['style'] = 'caption-side: top; background-color: #eee; padding: 8px'
			
			for a_td in a_table_detail.findAll('td'):
				a_td['style'] = 'padding: 8px; border: 1px solid; border-color: #eee;'
				if 'left' in str(a_td.get('class')):
					a_td['style'] = a_td['style'] + ' width: 40%; font-weight: 700'
			
			product_description = product_description + str(a_table_detail)
	
	"""
	div_images = soup.find('div', {"class":"prd_productImages__verticalImageControlWrapper"})
	if div_images != None:
		image_count = 0;
		ul_images = div_images.find('ul')
		for a_li_image in ul_images.findAll('li'):
			if (image_count == max_images):
				break
			product_images.append(patch_image_src_otto(a_li_image.find('img').get('src')))
			image_count = image_count + 1
	if image_count == 0:
		div_images = soup.find('div', {"class":"prd_mainImageWithSwiping prd_mainImageWithSwiping--increaseHeight js_prd_mainImageWithSwiping"})
		img = div_images.find('img')
		product_images.append(patch_image_src_otto(img.get('src')))
	"""
		
	upload_product(product_name, product_description, product_price, product_images, product_number, product_articleNr, product_manufacturer, product_ean, product_categories, product_variant)
	
def get_products_otto(soup):
	for a_article in soup.findAll('article'):
		a_href = a_article.find('a', {"class":"productLink"})
		a_link = "https://www.otto.de" + a_href.get('href')
		#product_number = 'OT' + a_article.get('data-articlenumber')
		
		get_a_product_otto(a_link)
		#break # for test

def main_otto(baseurl):
	url = baseurl
	
	while True:	
		pprint('>> Scraping page \"' + url + '\"\n')
		soup = get_content_url(url)
		#write_to_file("apage.txt", soup) # for test
		#soup = read_from_file("apage.txt") # for test
		
		get_products_otto(soup)
		#break # for test
		
		paging_block = soup.find('div', {"class":"san_paging__bottomWrapper"})
		ul = None
		if paging_block != None:
			ul = paging_block.find('ul')
			
		next_url = get_next_page_otto(ul)
		if next_url == '':
			break
		
		url = baseurl + "?" + str(next_url)
		
# fahrrad-xxl.de functions
"""
def get_pages_count_fahrrad(ul):
	total_pages = '1'
	if ul != None:
		for a_li in ul.findAll('li'):
			if 'fxxl-pager-bottom__item--next' in a_li.get('class'):
				break
			a_href = a_li.find('a')
			if a_href != None:
				total_pages = a_href.text
	print('there are total ' + total_pages + ' pages');
"""

def get_next_page_fahrrad(ul):
	data_page = ''
	if ul != None:
		_break = False
		for a_li in ul.findAll('li'):
			if _break == True:
				data_page = str(a_li.find('a').get('href'))
				break;
			if 'fxxl-pager-bottom__item--current' in a_li.get('class'):
				_break = True
	return data_page

def patch_string(str):
	str = str.replace('.', '')
	str = str.replace(',', '.')
	new_str = ''
	for ch in str:
		if ch == '.' or (ch >= '0' and ch <= '9'):
			new_str = new_str + ch
	#if new_str[-1] == '.':
	#	new_str = new_str[:-1]
	return new_str

def get_a_product_fahrrad(url):
	product_name = ''
	product_price = 0.0
	product_description = ''
	product_number = ''
	product_articleNr = ''
	product_manufacturer = 'supplier'
	product_images = json.loads('[]')
	product_eans = json.loads('[]')
	product_categories = json.loads('[]')
	product_variant = json.loads('[]')
	
	pprint('>>> Uploading product \"' + url + '\"\n')
	soup = get_content_url(url)
	if soup == '':
		return
	
	div_detail_buybox = soup.find('div', {"class":"fxxl-artikel-detail__buy-box"})
	if div_detail_buybox == None:
		return
	div_select = div_detail_buybox.find('select')
	if div_select != None:
		for a_option in div_select.findAll('option'):
			if a_option.has_attr('disabled') == False:
				product_variant.append(a_option.text)
	else:
		product_variant.append('')
	
	div_detail = div_detail_buybox.find('div', {"class":"fxxl-artikel-detail__buy-box-s1 fxxl-container-mwd0"})
	product_name = div_detail.find('h1').text
	product_manufacturer = product_name.split(' ')[0]
	
	div_brand = soup.find('a', {"class":"fxxl-artikel-detail__brand gtm__artikel--brand"})
	if div_brand != None:
		div_brand_img = div_brand.find('img')
		if div_brand_img != None:
			product_manufacturer = div_brand_img.get('title')
		else:
			product_manufacturer = div_brand.text
		
	div_articleNr = soup.find('div', {"fxxl-artikel-detail__productno"})
	if div_articleNr != None:
		product_articleNr = div_articleNr.find('span').text
		
	div_products = div_detail_buybox.select('div[class*="fxxl-artikel-detail__buy-box-s2"]')
	try:
		div_products = div_products[0].find('script')
		div_products = str(div_products.contents[0])
		div_products = div_products.split('};')[0]
		div_products = div_products.split('et.data.pvdVariantSelectorMap=')[1]
		json_products = json.loads(div_products + '}')
		for json_key in json_products.keys():
			json_product = json_products[json_key]
			product_eans.append(json_product['ean'])
	except:
		pprint('>>>> EAN parse error\n')
		return
		
	div_categories = soup.find('ul', {"class":"fxxl-breadcrumb fxxl-container"})
	if div_categories != None:
		for a_li_category in div_categories.findAll('li', {"class":"fxxl-breadcrumb__element gtm__breadcrumb--element"}):
			product_categories.append(a_li_category.find('a').text)
	
	div_price = div_detail.find('div', {"class":"fxxl-artikel-detail__price-container"})
	if div_price != None:
		div_actual_price = div_price.find('div', {"class":"fxxl-artikel-detail__price fxxl-price-with-strike-price"})
		if div_actual_price == None:
			div_actual_price = div_price.find('div', {"class":"fxxl-artikel-detail__price fxxl-price"})
		
		product_price = float(patch_string(div_actual_price.text))
		if (product_price > max_price_filter):
			pprint('>>>> Skipped by price filter.\n')
			return
		if (product_price < min_price_filter):
			pprint('>>>> Skipped by price filter.\n')
			return
		product_price = (100 - random.randint(min_price_reduction, max_price_reduction)) * product_price / 100
		if is_round == True:
			product_price = round(product_price)
	
	div_section = soup.find('div', {"class":"fxxl-artikel-detail__section_content1 pvd-d__content"})
	if div_section != None:
		div_description = div_section.find('div', {"class":"pvd-d__text1"})
		if div_description == None:
			div_description = div_section.find('div', {"class":"pvd-d__text2"})
		if div_description == None:
			div_description = div_section.find('div', {"class":"pvd-d__texts"})
		if div_description != None:
			for a_image in div_description.findAll('img'):
				if 'lazyload' in str(a_image.get('class')):
					a_image['src'] = a_image.get('data-src')
			product_description = str(div_description.decode_contents())
		
	div_details = soup.find('div', {"class":"fxxl-artikel-detail__section_content1 pvd-a__content"})
	if div_details != None:
		for a_div_grid in div_details.findAll('div', {"class":"fxxl-artikel-detail__grouping-properties-grid"}):
			table_soup = BeautifulSoup('<table style="margin-top: 16px; width: 100%"><tbody></tbody></table>', "lxml")
			
			a_tr_tag = None
			for a_ch_div in a_div_grid.findAll('div'):
				if 'title' in str(a_ch_div.get('class')):
					a_caption_tag = table_soup.new_tag('caption', style='caption-side: top; background-color: #eee; padding: 8px')
					a_caption_tag.string = a_ch_div.text
					table_soup.table.insert(0, a_caption_tag)
				else:
					td_class = ''
					if a_ch_div.get('data-column') == "1":
						a_tr_tag = table_soup.new_tag('tr')
						table_soup.table.tbody.append(a_tr_tag)
						td_class = 'width: 40%; font-weight: 700; '
					if a_tr_tag != None:
						td_class = td_class + 'padding: 8px; border: 1px solid; border-color: #eee;'
						a_td_tag = table_soup.new_tag('td', style=td_class)
						a_td_tag.string = a_ch_div.text
						table_soup.findAll('tr')[-1].append(a_td_tag)
			a_div_grid = table_soup.find('table')
			product_description = product_description + str(a_div_grid)
	
	div_images_box = soup.find('div', {"class":"fxxl-artikel-detail__images-box fxxl-container-mwd0"})
	div_current_visible = None
	for a_div_product in div_images_box.select('div[class*="fxxl-vc-product"]'):
		if 'fxxl-vc-visible' in str(a_div_product.get('class')):
			div_current_visible = a_div_product
			break
	if div_current_visible != None:
		div_images = div_current_visible.find('div', {"class":"fxxl-artikel-detail-slider1"})
		if div_images != None:
			image_count = 0;
			div_slider_images = div_images.find('div', {"class":"fxxl-touch-slider__container fxxl-touch-slider--horizontal"})
			if div_slider_images != None:
				for a_div_image in div_slider_images.findAll('div'):
					if (image_count == max_images):
						break
					a_image = a_div_image.find('img').get('data-src');
					if a_image == None:
						a_image = a_div_image.find('img').get('src');
					product_images.append(patch_image_src_otto(a_image))
					image_count = image_count + 1
	upload_product(product_name, product_description, product_price, product_images, product_number, product_articleNr, product_manufacturer, product_eans, product_categories, product_variant)
	
def get_products_fahrrad(soup):
	for a_article in soup.findAll("div", {"class":'fxxl-element-artikel'}):
		a_href = a_article.find('a')
		a_link = a_href.get('href')
		#product_number = 'FX' + a_href.get('data-artikelnr')
		
		get_a_product_fahrrad(a_link)
		#break # for test
		
def main_fahrrad(start_url):
	baseurl = "https://www.fahrrad-xxl.de"
	url = start_url
	
	while True:
		pprint('>> Scraping page \"' + url + '\"\n')
		soup = get_content_url(url)
		#write_to_file("apage.txt", soup) # for test
		#soup = read_from_file("apage.txt") # for test
		
		get_products_fahrrad(soup)
		#break # for test
		
		paging_block = soup.find('div', {"class":"fxxl-product-pager-bottom"})
		ul = None
		if paging_block != None:
			ul = paging_block.find('ul')

		next_url = get_next_page_fahrrad(ul)
		if next_url == '':
			break
		
		url = baseurl + next_url

# mediamarkt.de functions

def check_hcaptcha_mediamarkt(url, soup):
	global mediamarkt_driver
	if soup.find('form', id='challenge-form') == None:
		return soup

	div_captcha = None
	
	while True:
		content = mediamarkt_driver.page_source
		soup = BeautifulSoup(content, 'lxml')
		
		div_captcha = soup.find(id='cf-hcaptcha-container')
		if div_captcha != None:
			break
		time.sleep(1)
		
	form_captcha = div_captcha.find('iframe')
	sitekey = form_captcha.get('src')
	sitekey = sitekey.split('sitekey=')
	if len(sitekey) == 2:
		sitekey = sitekey[1]
	else:
		sitekey = None
	
	if sitekey == None:
		mediamarkt_driver.close()
		mediamarkt_driver = None
		return soup
	
	pprint('>>> Solving captcha...\n')
	solver = TwoCaptcha(captcha_api_key)
	result = solver.hcaptcha(
		sitekey=sitekey,
		url=url,
	)
	
	pprint('>>> Captcha solved. Redirecting to page...\n')
	mediamarkt_driver.execute_script('document.getElementsByName("h-captcha-response")[0].innerHTML = "' + result['code'] + '"')
	mediamarkt_driver.find_element_by_id("challenge-form").submit()

	content = mediamarkt_driver.page_source
	soup = BeautifulSoup(content, 'lxml')
	return soup

def get_content_mediamarkt(url):
	if mediamarkt_driver == None:
		init_mediamarkt_driver('https://www.mediamarkt.de')
	mediamarkt_driver.get(url)
	content = mediamarkt_driver.page_source
	soup = BeautifulSoup(content, 'lxml')
	return check_hcaptcha_mediamarkt(url, soup)

def init_mediamarkt_driver(url):
	global mediamarkt_driver
	
	options = webdriver.ChromeOptions()
	options.add_experimental_option('excludeSwitches', ['enable-logging'])
	mediamarkt_driver = webdriver.Chrome(executable_path=r"py/chromedriver.exe", options=options)
	#driver.set_window_position(-10000, 0)
	#driver.set_window_size(10, 10)
	mediamarkt_driver.get(url)

def add_to_table(name, features, table_soup):
	a_caption_tag = table_soup.new_tag('caption', style='caption-side: top; background-color: #eee; padding: 8px')
	a_caption_tag.string = name
	table_soup.table.insert(0, a_caption_tag)
	
	a_tr_tag = None
	for a_feature in features:
		td_class = ''
		
		a_tr_tag = table_soup.new_tag('tr')
		table_soup.table.tbody.append(a_tr_tag)
		
		td_class = 'width: 40%; font-weight: 700; padding: 8px; border: 1px solid; border-color: #eee;'
		a_td_tag = table_soup.new_tag('td', style=td_class)
		a_td_tag.string = a_feature['name']
		table_soup.findAll('tr')[-1].append(a_td_tag)
		
		td_class = 'padding: 8px; border: 1px solid; border-color: #eee;'
		a_td_tag = table_soup.new_tag('td', style=td_class)
		a_td_tag.string = a_feature['value']
		if a_feature['unit'] != None:
			a_td_tag.string = a_td_tag.string + ' ' + a_feature['unit']
		table_soup.findAll('tr')[-1].append(a_td_tag)

def get_product_mediamarkt(url):
	product_name = ''
	product_price = 0.0
	product_description = ''
	product_number = ''
	product_articleNr = ''
	product_images = json.loads('[]')
	product_manufacturer = ''
	product_eans = json.loads('[]')
	product_categories = json.loads('[]')
	product_variant = json.loads('[]')
	product_variant.append('')

	pprint('>>> Uploading product \"' + url + '\"\n')
	soup = get_content_mediamarkt(url)
	#write_to_file("aproduct.txt", soup) # for test
	#soup = read_from_file("aproduct.txt") # for test
	
	div_details_header = soup.find('div', {"data-test": "mms-select-details-header"})
	if div_details_header == None:
		return
	product_name = div_details_header.find('h1').text
	
	div_manufacturers = div_details_header.select('div[class*="dVcySS"]')
	if len(div_manufacturers) == 0:
		product_manufacturer = product_name.split(' ')[0]
	else:
		product_manufacturer = div_manufacturers[0].find('img').get('alt')
	
	product_articleNr = div_details_header.select('span[class*="ezMJh"]')[0].text
	product_articleNr = product_articleNr.split('.')[2]
	product_articleNr = product_articleNr.split(' ')[1]
	product_number = 'MM' + product_articleNr
	
	product_categories.append('Startseite');
	div_categories = soup.find('div', {"data-test": "mms-breadcrumb-v2-ul"})
	if div_categories != None:
			ul_categories = div_categories.find('ul')
			for a_li_category in ul_categories.findAll('li'):
				a_categories = a_li_category.find('a').select('span[class*="Uqzhg"]')
				if (len(a_categories) > 0):
					product_categories.append(a_categories[0].text)
	
	div_script = None
	for a_div_script in soup.findAll('script'):
		if 'window.__PRELOADED_STATE__'.lower() in str(a_div_script).lower():
			div_script = a_div_script.contents[0]
			div_script = div_script[div_script.index('{'):]
			if div_script[-1] == ';':
				div_script = div_script[:-1]
			break
			
	a_table_detail = ''

	
	try:
		json_products = json.loads(div_script)['apolloState']
		for json_key in json_products.keys():
			if 'Product:' in json_key:
				json_product = json_products[json_key]
				product_eans.append(str(json_product['ean']))
				
				image_count = 0
				for a_json_asset in json_product['assets']:
					if (image_count == max_images):
						break
					if a_json_asset['usageType'] != 'Product Image':
						continue
					product_images.append(patch_image_src_otto(a_json_asset['link'] + '/fee_786_587_png'))
					image_count = image_count + 1

				table_soup = BeautifulSoup('<table style="margin-top: 16px; width: 100%"><tbody></tbody></table>', "lxml")
				add_to_table('Highlights', json_product['mainFeatures'], table_soup)
				a_table_detail = a_table_detail + str(table_soup.find('table'))
				
				for a_json_feature in json_product['featureGroups']:
					table_soup = BeautifulSoup('<table style="margin-top: 16px; width: 100%"><tbody></tbody></table>', "lxml")
					add_to_table(a_json_feature['featureGroupName'], a_json_feature['features'], table_soup)
					a_table_detail = a_table_detail + str(table_soup.find('table'))
				
				break
	except:
		pprint('>>>> EAN parse error\n')
		return
	
	div_price = soup.select('div[class*="qMGmj"]')
	if len(div_price) > 0:
		div_price = div_price[0]
		whole_price = div_price.select('span[class*="fDRbzs"]')[0].text
		whole_price = whole_price.split('.')[0]
		decimal_price = div_price.select('sup[class*="eItlCh"]')[0].text
		if decimal_price == '':
			decimal_price = '0'
		product_price = float(whole_price) + float(decimal_price) / 100
		if (product_price > max_price_filter):
			pprint('>>> Skipped by price filter.\n')
			return
		if (product_price < min_price_filter):
			pprint('>>> Skipped by price filter.\n')
			return
		product_price = (100 - random.randint(min_price_reduction, max_price_reduction)) * product_price / 100
		if is_round == True:
			product_price = round(product_price)
	
	"""
	div_gallery = soup.find('div', {"data-test": "mms-select-gallery"})
	if div_gallery != None:
		image_count = 0;
		ul_images = div_gallery.find('ul')
		for a_li_image in ul_images.findAll('li'):
			if (image_count == max_images):
				break
			a_img_src = a_li_image.find('source')
			if a_img_src != None:
				product_images.append(patch_image_src_otto(a_img_src.get('srcset')))
				image_count = image_count + 1
	"""
			
	section_description = soup.find(id='description')
	div_description = soup.find('div', {"data-test": "mms-accordion-description"}).find('div')
	for a_href_desc in div_description.select('a'):
		a_href_desc.extract()
	product_description = str(div_description.decode_contents())
	
	"""
	section_features = soup.find(id='features')
	div_features = soup.find('div', {"data-test": "mms-accordion-features"}).find('div')
	
	if div_features != None:
		for a_table_detail in div_features.findAll('table'):
			a_table_detail['padding'] = '8px 8px 6px'
			a_table_detail['style'] = 'margin-top: 16px; width: 100%'
			a_caption = a_table_detail.find('thead')
			a_caption['style'] = 'background-color: #eee;'
			a_th = a_caption.find('th')
			a_th['style'] = 'padding: 8px;'
			
			for a_td in a_table_detail.findAll('td'):
				a_td['style'] = 'padding: 8px; border: 1px solid; border-color: #eee;'
				if 'kqRXoX' in str(a_td.get('class')):
					a_td['style'] = a_td['style'] + ' width: 40%; font-weight: 700'
	"""
			
	product_description = product_description + str(a_table_detail)

	upload_product(product_name, product_description, product_price, product_images, product_number, product_articleNr, product_manufacturer, product_eans, product_categories, product_variant)
		
def main_mediamarkt(baseurl, page_mark):
	origurl = 'https://www.mediamarkt.de'

	current_page = 1
	while True:
		item_found = 0
		
		url = baseurl + page_mark + 'page=' + str(current_page)
		pprint('>> Scraping page \"' + url + '\"\n')
		soup = get_content_mediamarkt(url)
		#write_to_file("apage.txt", soup) # for test
		#soup = read_from_file("apage.txt") # for test
		
		for div_product in soup.findAll('div', {"data-test": "mms-search-srp-productlist-item"}):
			a_href = div_product.find('a')
			if a_href == None:
				continue
			item_found = item_found + 1
			a_link = origurl + a_href.get('href')
			get_product_mediamarkt(a_link)
			#return # for test
		if item_found == 0:
			break
		current_page = current_page + 1

def keyword_search_otto(keyword):
	keyword = keyword.replace(" ", "%20")
	main_otto("https://www.otto.de/suche/" + keyword + "/")

def url_search_otto(url):
	main_otto(url)
	
def single_search_otto(url):
	get_a_product_otto(url)
	
def keyword_search_fahrrad(keyword):
	keyword = keyword.replace(" ", "+")
	main_fahrrad("https://www.fahrrad-xxl.de/suche/?q=" + keyword + "/")

def url_search_fahrrad(url):
	main_fahrrad(url)

def single_search_fahrrad(url):
	get_a_product_fahrrad(url)
	
def keyword_search_mediamarkt(keyword):
	keyword = keyword.replace(" ", "+")
	main_mediamarkt("https://www.mediamarkt.de/de/search.html?query=" + keyword, '&')

def url_search_mediamarkt(url):
	main_mediamarkt(url, '?')

def single_search_mediamarkt(url):
	get_product_mediamarkt(url)

def read_config():
	global is_upload_to_shopware
	global str_keyword
	global is_search_by_keyword
	global max_products
	global max_images
	global min_price_reduction
	global max_price_reduction
	global min_price_filter
	global max_price_filter
	global captcha_api_key
	global is_otto
	global is_mediamarkt
	global is_fahrrad
	global str_urls
	global prestashop
	global shopware
	global shopware_categories
	global is_round00
	global title_search
	global single_url
	
	shopware_admin = ''
	shopware_api_key = ''
	shopware_url = ''
	presta_api_key = ''
	presta_url = ''
	
	config = configparser.ConfigParser()
	config.read(r'settings.ini', 'utf-8')
	
	shopware_admin = config.get('General', 'shopware_admin')
	shopware_api_key = config.get('General', 'shopware_api_key')
	shopware_url = config.get('General', 'shopware_url')
	presta_api_key = config.get('General', 'presta_api_key')
	presta_url = config.get('General', 'presta_url')
	is_upload_to_shopware = config.get('General', 'isShopware') == 'true'
	str_keyword = config.get('General', 'keyword')
	single_url = config.get('General', 'singleUrl')
	is_search_by_keyword = int(config.get('General', 'currentTab'))
	max_products = int(config.get('General', 'max_products'))
	max_images = int(config.get('General', 'max_images'))
	min_price_reduction = int(config.get('General', 'min_price_reduction'))
	max_price_reduction = int(config.get('General', 'max_price_reduction'))
	min_price_filter = int(config.get('General', 'min_price_filter'))
	max_price_filter = int(config.get('General', 'max_price_filter'))
	captcha_api_key = config.get('General', 'captcha_api_key')
	is_otto = config.get('General', 'otto') == 'true'
	is_mediamarkt = config.get('General', 'mediamarkt') == 'true'
	is_fahrrad = config.get('General', 'fahrrad') == 'true'
	str_urls = config.get('General', 'url').split('\\n')
	is_round00 = config.get('General', 'isRound00') == 'true'
	title_search = config.get('General', 'title_search') == 'true'
	
	
	if is_upload_to_shopware:
		shopware = rest.client_from_env(shopware_admin, shopware_api_key, shopware_url + '/api')
		shopware_categories = shopware.get_categories()
	else:
		prestashop = presta.PrestashopApi(presta_url + '/api', presta_api_key)
		get_categories_prestashop()
		get_manufacturers_prestashop()
	
def main():
	pprint('----- MultiGrabber started -----\n')
	pprint('Reading config...\n')
	read_config()
	
	if is_search_by_keyword == 0: # scrape by keyword
		pprint('> Scraping by keyword \"' + str_keyword + '\"...\n')
		if is_otto:
			keyword_search_otto(str_keyword)
		if is_fahrrad:
			keyword_search_fahrrad(str_keyword)
		if is_mediamarkt:
			keyword_search_mediamarkt(str_keyword)
	if is_search_by_keyword == 1: # scrape by urls
		for url in str_urls:
			pprint('> Scraping by url \"' + url + '\"...\n')
			if 'www.otto.de' in url:
				url_search_otto(url)
			if 'www.fahrrad-xxl.de' in url:
				url_search_fahrrad(url)
			if 'www.mediamarkt.de' in url:
				url_search_mediamarkt(url)
	if is_search_by_keyword == 2: # scrape by urls
		url = single_url
		url = url.replace('"', '')
		pprint('> Scraping single product \"' + url + '\"...\n')
		if 'www.otto.de' in url:
			single_search_otto(url)
		if 'www.fahrrad-xxl.de' in url:
			single_search_fahrrad(url)
		if 'www.mediamarkt.de' in url:
			single_search_mediamarkt(url)
	exit_me()
	
main()