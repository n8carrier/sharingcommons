from google.appengine.ext import ndb
from datetime import datetime,timedelta
import logging
from src.accounts.models import UserAccount
import urllib
from google.appengine.api import urlfetch
import json

class Item(ndb.Model):
	"""Cached representation of an item"""
	item_key = ndb.StringProperty(required=True) #Unique, Key
	item_type = ndb.StringProperty(required=True)
	last_update = ndb.DateTimeProperty()
	title = ndb.StringProperty(required=True)
	thumbnail_link = ndb.StringProperty(required=True)
	description = ndb.TextProperty(required=False)
	author = ndb.StringProperty(required=False)
	year = ndb.IntegerProperty(required=False)
	genre = ndb.StringProperty(required=False)
	rating = ndb.StringProperty(required=False)
	direct_link = ndb.StringProperty(required=False)
	
	def update_cache(self):
		#update cached information about the item using the external apis
		if self.item_key:
			logging.debug("update_cache(%s)" % self.item_key)
			if self.item_type == "movie":
				RT_Key = True #specify that you're searching a rotten tomatoes key, not executing a query
			else:
				RT_Key = False
			Item.search_by_attribute(self.item_type,self.item_key, None, True, RT_Key)

	def cache_expired(self):
		"""determine if the cached information in the database needs to be refreshed
		
		"""
		if self.last_update:
			return (datetime.now() - self.last_update) > timedelta(days=1)
		else:
			True
	
	@classmethod
	def get_by_key(cls,item_type,item_key=None):
		"""Convert an item_key to an Item object
		
		Arguments:
		item_key -- the item_key being searched
		
		Return value:
		An instance of an Item object with the given item_key; if the key could not be resolved
		to an Item object, returns None
		
		"""
		if not item_key:
			logging.error("Item.get_by_key() called without a key")
			return None
		logging.debug("Item.get_by_key(%s)" % item_key)
		item = Item.query(Item.item_key==item_key).get()
		if item:
			logging.debug("item_key:%s was found in the item cache" % item_key)
			if item.cache_expired():
				item.update_cache()
		else:
			logging.debug("item_key:%s not found in cache; performing external search" % item_key)
			item = Item(item_key=item_key,item_type=item_type)
			item.update_cache()
			item = Item.query(Item.item_key==item_key).get()
		return item
	
	@classmethod
	def search_by_attribute(self, item_type, value, attribute = None, cache = False, RT_Key = False):
		itemlist = []
		if item_type == 'book':
			# Search with 'attribute = None' when searching for an OLID
			value = urllib.quote(value)
			if(attribute == None):
				query = "q=" + value
			elif(attribute == "ISBN"):
				query = "isbn=" + value
			elif(attribute == "title"):
				query = "title=" + value
			elif(attribute == "author"):
				query = "author=" + value
			else:
				logging.debug("Item.search_by_attribute() was called with an invalid attribute: %s" %attribute)
				return itemlist
			url = "http://openlibrary.org/search.json?" + query
			response = urlfetch.fetch(url=url, deadline=10)
			counter = 0
			try:
				if response.status_code == 200:
					json_response = response.content
					data = json.loads(json_response)
					for book in data['docs']:
						if cache:
							# Check to see if Item is already in the database; if so, update that copy
							checkItem = Item.query(Item.item_key==book['key']).get()
							if checkItem:
								curItem = checkItem
								createNew = False
							else:
								createNew = True
						else:
							createNew = True
							
						if createNew:
							curItem = Item(item_key=None)
							curItem.item_type = "book"
							curItem.item_key = book['key']
							
						if 'title' in book:
							curItem.title = book['title']
						else:
							curItem.title = ""
					
						if 'author_name' in book:
							curItem.author = book['author_name'][0]
							for i in range(1, len(book['author_name'])):
								curItem.author += ", " + book['author_name'][i]
						else:
							curItem.author = ""
					
						if 'cover_i' in book:
							curItem.thumbnail_link = "http://covers.openlibrary.org/b/id/" + str(book['cover_i']) + "-M.jpg"
						else:
							curItem.thumbnail_link = ""
					
						curItem.last_update = datetime.now()
						if cache:
							curItem.put()
						itemlist.append(curItem.to_dict())
						counter += 1
			except:
				pass
		elif item_type == 'movie':
			query = value
			apikey = "f4dr8ebyf9pmh4wskegrs3vt"
			logging.info("RT API Key, updated 5/10")
			if not RT_Key:
				url = "http://api.rottentomatoes.com/api/public/v1.0/movies.json?apikey=" + apikey + "&q=" + query + "&page_limit=50"
				response = urlfetch.fetch(url=url, deadline=10)
				try:
					logging.debug("RT Status Code: %s" %response.status_code)
					if response.status_code == 200:
						json_response = response.content
						data = json.loads(json_response)
						for movie in data['movies']:
							if cache:
								# Check to see if Item is already in the database; if so, update that copy
								checkItem = Item.query(Item.item_key==movie['id']).get()
								if checkItem:
									curItem = checkItem
									createNew = False
								else:
									createNew = True
							else:
								createNew = True
								
							if createNew:
								# Build itemlist of movies
								curItem = Item(item_key=None)
								curItem.item_type = "movie"
								curItem.item_key = movie['id']
							
							curItem.title = movie['title']
							if isinstance(movie.get('year',9999),(int,long)):
								curItem.year = movie.get('year',9999)
							else:
								curItem.year = 9999
							curItem.rating = movie.get('mpaa_rating',"Rating Not Available")
							curItem.description = movie.get('synopsis',"Synopsis Not Available")
							curItem.thumbnail_link = movie['posters'].get('thumbnail','')
							curItem.direct_link = movie['links'].get('alternate','')
							# To get genre, open detail page (but only do it when caching since it will be slow with many movies)
							if cache:
								url = movie['links']['self'] + "?apikey=" + apikey
								response_detail = urlfetch.fetch(url=url, deadline=10)
								try:
									if response_detail.status_code == 200:
										json_response_detail = response_detail.content
										data =  json.loads(json_response_detail)
										curItem.genre = data['genres'][0]
										for i in range(1, len(data['genres'])):
											curItem.genre += ", " + data['genres'][i]
								except:
									curItem.genre = ""
								curItem.last_update = datetime.now()
								if cache:
									curItem.put()
							itemlist.append(curItem.to_dict())
				except:
					pass
			else:
				# Searching for a specific Rotten Tomatoes key (Rotten Tomatoes does not send you to the direct movie link with a search query, so it's necessary to access it directly)
				url = "http://api.rottentomatoes.com/api/public/v1.0/movies/" + value + ".json?apikey=" + apikey
				response_detail = urlfetch.fetch(url)
				try:
					if response_detail.status_code == 200:
						json_response_detail = response_detail.content
						movie = json.loads(json_response_detail)
						if cache:
							# Check to see if Item is already in the database; if so, update that copy
							checkItem = Item.query(Item.item_key==value).get()
							if checkItem:
								curItem = checkItem
								createNew = False
							else:
								createNew = True
						else:
							createNew = True
							
						if createNew:
							curItem = Item(item_key=None)
							curItem.item_type = "movie"
							curItem.item_key = value
							
						curItem.title = movie['title']
						if isinstance(movie.get('year',9999),(int,long)):
							curItem.year = movie.get('year',9999)
						else:
							curItem.year = 9999
						curItem.rating = movie.get('mpaa_rating',"Rating Not Available")
						curItem.description = movie.get('synopsis',"Synopsis Not Available")
						curItem.thumbnail_link = movie['posters'].get('thumbnail','')
						curItem.direct_link = movie['links'].get('alternate','')
						curItem.genre = movie['genres'][0]
						for i in range(1, len(movie['genres'])):
							curItem.genre += ", " + movie['genres'][i]
						curItem.last_update = datetime.now()
						if cache:
								curItem.put()
						itemlist.append(curItem.to_dict())
				except:
					pass
		return itemlist

class ItemCopy(ndb.Model):
	"""A model for linking User to Item
	
	This method was chosen over a List object on the User Account because this allows more 
	flexibility for adding additional information about a particular copy of a Item
	
	"""
	
	item = ndb.KeyProperty(kind=Item)
	item_subtype = ndb.StringProperty(required=False)
	owner = ndb.KeyProperty(kind=UserAccount)
	borrower = ndb.KeyProperty(kind=UserAccount)
	due_date = ndb.DateProperty()
	star_rating = ndb.StringProperty(required=False)
	manual_borrower_name = ndb.StringProperty(required=False)
	manual_borrower_email = ndb.StringProperty(required=False)
	
	def get_owner(self):
		owner = UserAccount.get_by_id(self.owner.id())
		return owner.name
		
	def get_borrower(self):
		borrower = UserAccount.get_by_id(self.borrower.id())
		return borrower.name

	def display(self):
		item = Item.query(Item.key == self.item).get()
		return item.title

	def lend(self, borrowerID, date = None):
		import datetime
		borrower = UserAccount.getuser(borrowerID)
		owner = UserAccount.get_by_id(self.owner.id())
		self.borrower = borrower.key
		if(date):
			self.due_date = datetime.datetime.strptime(date, '%Y-%m-%d');
		else:
			self.due_date = datetime.datetime.now() + datetime.timedelta(days=int(owner.lending_length))

	def return_item(self):
		self.borrower = None
		self.due_date = None
		self.manual_borrower_name = None
		self.manual_borrower_email = None

	def update_due_date(self, date):
		import datetime
		self.due_date = date

	def get_due_date(self):
		return self.due_date
		
	def update_star_rating(self, star_rating):
		self.star_rating = star_rating
		self.put()
		return True


