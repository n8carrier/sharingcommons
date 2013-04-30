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
	author_director = ndb.StringProperty(required=True)
	thumbnail_link = ndb.StringProperty(required=True)
	
	def update_cache(self):
		#update cached information about the item using the external apis
		if self.item_key:
			logging.debug("update_cache(%s)" % self.item_key)
			Item.search_by_attribute("book",value=self.item_key, attribute=None, cache=True)

	def cache_expired(self):
		"""determine if the cached information in the database needs to be refreshed
		
		"""
		return (datetime.now() - self.last_update) > timedelta(minutes=1000)
	
	@classmethod
	def get_by_key(cls,item_key=None):
		"""Convert an item_key to an Item object
		
		Arguments:
		item_key -- the item_key being searched
		
		Return value:
		An instance of an Item object with the given item_key; if the key could not be resolved
		to an Item object, returns None
		
		"""
		if not item_key:
			logging.error("Item.get_by_key() called without an open library key")
			return None
		logging.debug("Item.get_by_key(%s)" % item_key)
		item = Item.query(Item.item_key==item_key).get()
		if item:
			logging.debug("item_key:%s was found in the item cache" % item_key)
			if item.cache_expired():
				item.update_cache()
		else:
			logging.debug("item_key:%s not found in cache; performing external search" % item_key)
			item = Item(item_key=item_key)
			item.update_cache()
			item = Item.query(Item.item_key==item_key).get()
		return item
	
	@classmethod
	def search_by_attribute(self, item_type, value, attribute = None, cache = False):
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
			response = urlfetch.fetch(url)
			counter = 0
			try:
				if response.status_code == 200:
					json_response = response.content
					data = json.loads(json_response)
					for book in data['docs']:
						curItem = Item(item_key=None)
						curItem.item_type = "book"
						curItem.item_key = book['key']
						if 'title' in book:
							curItem.title = book['title']
						else:
							curItem.title = ""
					
						if 'author_name' in book:
							curItem.author_director = book['author_name'][0]
							for i in range(1, len(book['author_name'])):
								curItem.author_director += ", " + book['author_name'][i]
						else:
							curItem.author_director = ""
					
						if 'cover_i' in book:
							curItem.thumbnail_link = "http://covers.openlibrary.org/b/id/" + str(book['cover_i']) + "-M.jpg"
						else:
							curItem.thumbnail_link = ""
					
						curItem.last_update = datetime.now()
						if cache == True:
							curItem.put()
						itemlist.append(curItem.to_dict())
						counter += 1
			except:
				pass
		#elif item_type == 'movie':
			#build itemlist of movies
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

	def update_due_date(self, date):
		import datetime
		self.due_date = date

	def get_due_date(self):
		return self.due_date


