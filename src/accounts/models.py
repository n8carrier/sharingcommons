from google.appengine.ext import ndb
from google.appengine.api import users
from google.appengine.api.datastore import Key
from datetime import datetime,timedelta
from flaskext.login import AnonymousUser
from werkzeug.security import generate_password_hash, check_password_hash
import logging


class Connection(ndb.Model): 
	user = ndb.KeyProperty(kind="UserAccount")


class UserAccount(ndb.Model):
	"""Stored information about a User"""
	
	name = ndb.StringProperty(required=True)
	email = ndb.StringProperty(required=True)
	item_count = ndb.IntegerProperty(default=0)
	lending_length = ndb.StringProperty(default="14")
	notification = ndb.StringProperty(default="email")
	info = ndb.StringProperty(default="")
	custom_url = ndb.StringProperty(required=False)

	connected_accounts = ndb.StructuredProperty(Connection,repeated=True)
	
	@property
	def pending_actions(self):
		from src.activity.models import Action
		return Action.query(Action.useraccount == self.key).fetch()
	
	@property
	def connections(self):
		"""Get all the keys of all the users this user is connected to

		Return value:
		an array will all the keys of all the users this user is connected to
		"""
		return self.connected_accounts

	def get_network_items(self):
		"""Get all the items owned by users connected to this owned

		Return value:
		an array will all the ItemCopy objects belonging to connected users

		"""
		from src.items.models import ItemCopy
		return ItemCopy.query(ItemCopy.owner.IN(self.get_connections())).fetch()
	
	def get_connections(self):
		"""Get all the users this user is connected to

		Return value:
		an array will all the user objects this user is connected to
		"""
		return UserAccount.query(UserAccount.connected_accounts.user == self.key).fetch(keys_only=True)
	
	def get_all_connections(self):
		"""Get all the users this user is connected to

		Return value:
		an array will all the user objects this user is connected to
		"""
		connections = []
		for connection in self.connected_accounts:
			connections.append(UserAccount.query(UserAccount.key==connection.user).get())
		return connections
	
	def update(self,name,lending_length,notifications,info):
		"""update the user's settings

		Arguments:
		name - the name the user would like to have displayed
		lending_length - the default number of days that this user lends out his/her items 
		notification - a string saying how this user will recieve notifications (email, mobile, both)
		info - a string, additional information about the user that will be displayed to other users
		
		Return value:
		True if successfull
		"""
		# validate name
		self.name = name
		self.lending_length = lending_length
		self.notification = notifications
		self.info = info
		self.put()
		return True

	def is_authenticated(self):
		"""determine whether the UserAccount is authenticated
		
		This method is required by the flask-login library
		
		Return value:
		True (note: the AnonymousUser object returns False for this method)
		
		"""
		return True

	def is_active(self):
		"""determine whether the UserAccount is active or not
		
		This method is required by the flask-login library
		
		Return value:
		True if the account is active; False otherwise
		
		"""
		return True

	def is_anonymous(self):
		"""determine whether the UserAccount is anonymous
		
		This method is required by the flask-login library
		
		Return value:
		False (note: the AnonymousUser object returns True for this method)
		
		"""
		return False

	def get_id(self):
		"""get the id for this UserAccount
		
		This method is required by the flask-login library
		
		Return value:
		Integer that represents the unique ID of this UserAccount
		
		"""
		return self.key.id()

	@classmethod
	def create_user(cls,g_user):
		if UserAccount.get_by_email(g_user.email()):
			return None
		user = UserAccount(name=g_user.nickname(),email=g_user.email())
		if user:
			user.put()
			return user
		else:
			return None

	@classmethod
	def can_delete_user(cls,user):
		"""Checks to see if a user can be deleted
		A user cannot be deleted if it is borrowing or lending items

		Return Value:
		True if it can be deleted, false if not
		"""
		borrowed = user.get_borrowed_items()
		lent = user.get_lent_items()
		if borrowed or lent:
			return None
		return True

	@classmethod
	def delete_user(cls,user):
		"""Deletes the given user from the system
		Also deletes the connection with each user it is connected to

		Arguments:
		user - The UserAccount object that should be deleted
		"""
		if UserAccount.can_delete_user(user):
			for connection in user.connections:
				user.remove_connection(connection,True)
			for copy in user.get_library():
				copy.key.delete()
			user.key.delete()
			return True
		return None

	@classmethod
	def getuser(cls,id):
		return UserAccount.get_by_id(id)
	
	@classmethod
	def get_by_email(cls,email):
		user = cls.query(cls.email==email).get()
		return user

	def get_library(self):
		"""retrieve the user's library
		
		Return value:
		list of ItemCopy objects owned by the user
		"""
		from src.items.models import ItemCopy
		return ItemCopy.query(ItemCopy.owner==self.key).fetch()
	
	def get_item(self,item_subtype,item):
		"""retrieve the user's copy of a particular item
		
		Arguments:
		item - the Item being retrieved

		Return value:
		the user's ItemCopy object associated with the provided Item; None if the user does not own item
		"""
		from src.items.models import ItemCopy
		myitem = ItemCopy.query(ItemCopy.item==item.key,ItemCopy.owner==self.key,ItemCopy.item_subtype==item_subtype).get()
		return myitem
	
	def add_item(self,item_subtype,item):
		"""add a personal copy of a item to a user's account
		
		Arguments:
		item - Item object being attached to the User

		Return Value:
		a ItemCopy instance that links the User to the Item; None if the Item could not be linked
		"""
		from src.items.models import ItemCopy
		itemcopy = ItemCopy(item=item.key,owner=self.key,item_subtype=item_subtype)
		if itemcopy.put():
			self.item_count = self.item_count + 1
			self.put()
		return itemcopy
		
	def remove_item(self,item_subtype,item):
		"""delete a user's copy of a item
		
		Arguments:
		item - Item object that is to be removed

		Return value:
		the ItemCopy instance that was just deleted; None if the ItemCopy was not found
		"""
		from src.items.models import ItemCopy
		itemcopy = ItemCopy.query(ItemCopy.item==item.key,ItemCopy.owner==self.key,ItemCopy.item_subtype==item_subtype).get()
		if itemcopy:
			itemcopy.key.delete()
			self.item_count = self.item_count - 1
			self.put()
		return itemcopy
	
	def send_invite(self, otherUser):
		"""sends an invite to another user

		Arguments:
		otherUser - a UserAccount object representing the user that should recieve the invite

		Return value:
		True if successfull, false if not
		"""
		from src.activity.models import ConnectionRequest
		connection = Connection(user=otherUser.key)
		if(connection in self.connected_accounts):
			return 1
		if(otherUser.get_id() == self.get_id()):
			return 2
		invitation = ConnectionRequest(useraccount=otherUser.key,connection=self.key)
		invitation.put()
		return 0

	def is_connected(self,otherUser):
		"""Check to see if this user is connected to the user given

		Arguments:
		otherUser - a UserAccount object representing the other user in question

		Return value:
		True if there exists a connection between the two users, False if notifications
		"""
		if self == otherUser:
			return True
		connection = Connection(user=otherUser.key)
		if(connection in self.connected_accounts):
			return True
		return False

	def add_connection(self, otherUser, reciprocate = True):
		"""add a connection with another user without worrying about invites and such
		(parameters and return values are the same as the previous method)
		"""
		connection = Connection(user=otherUser.key)
		if(connection in self.connected_accounts):
			return False
		self.connected_accounts.append(connection)
		self.put()
		if reciprocate:
			otherUser.add_connection(self, reciprocate = False)
		return True
		
	def remove_connection(self, otherUser, reciprocate = True):
		"""remove a connection with another user

		Arguments:
		otherUser - a UserAccount object representing the user with whom the connection should be removed
		reciprocate - whether or not the connection should also be removed from the other user as well

		Return value:
		True if successfull, false if not
		"""
		connection = Connection(user=otherUser.key)
		if(connection not in self.connected_accounts):
			return False
		self.connected_accounts.remove(connection)
		self.put()
		if reciprocate:
			otherUser.remove_connection(self, reciprocate = False)
		return True

	def create_invitation_link(self):
		return "manage_connections/" + str(self.get_id())

	def lend_item(self, itemID, borrowerID, due_date = None):
		"""Lend an item to another user

		Arguments:
		itemID: an ID representing the itemCopy object that will be lent out
		borrowerID: an ID representing the user that will borrow the item
		due_date: the date the item should be returned, 
			if none is given the default for the lender is used

		Return value:
		A string describing the success or failure of the operation
		"""
		from src.items.models import ItemCopy
		itemCopy = ItemCopy.get_by_id(itemID)

		# check to see if the item copy is valid
		if(itemCopy == None):
			return "Invalid item ID"
		if(itemCopy.owner != self.key):
			return "You do not own that item"
		if(itemCopy.borrower != None):
			return "That item is not avaiable to be lent out"

		itemCopy.lend(borrowerID, due_date)
		itemCopy.put()
		return "Item successfully lent"

	def borrow_item(self, itemID, lenderID, due_date = None):
		"""Borrow an item from another user

		Arguments:
		itemID: an ID representing the itemCopy object that will be borrowed
		lenderID: an ID representing the user that will lend the item
		due_date: the date the item should be returned, 
			if none is given the default for the lender is used

		Return value:
		A string describing the success or failure of the operation
		"""
		from src.items.models import ItemCopy
		itemCopy = ItemCopy.get_by_id(itemID)

		# check to see if the item copy is valid
		if(itemCopy == None):
			return "Invalid item ID"
		if(itemCopy.owner.id() != lenderID):
			return "That user does not own this item"
		if(itemCopy.borrower != None):
			return "That item is not avaiable to be lent out"

		itemCopy.lend(self.key.id(), due_date)
		itemCopy.put()
		return "Item successfully borrowed"

	def get_lent_items(self):
		"""Get all the items that the user is currently lending to anther user

		Return Value:
		A list of ItemCopy objects of all the the items the user is currently lending
		"""
		from src.items.models import ItemCopy
		return ItemCopy.query(ItemCopy.owner==self.key,ItemCopy.borrower!=None).fetch()

	def get_borrowed_items(self):
		"""Get all the items that the user is currently borrowing from anther user

		Return Value:
		A list of ItemCopy objects of all the the items the user is currently borrowing
		"""
		from src.items.models import ItemCopy
		return ItemCopy.query(ItemCopy.borrower==self.key).fetch()

	def return_item(self, itemCopyID):
		"""Return the given item to it's owner

		Arguments:
		itemCopyID: an ID representing a ItemCopy object, the item to be returned

		Return Value:
		A message describing the success or failure or the operation
		"""
		from src.items.models import ItemCopy
		from src.activity.models import ConfirmReturn
		itemcopy = ItemCopy.get_by_id(int(itemCopyID))

		# verify the itemCopyID was valid
		if(itemcopy == None):
			return "Invalid item ID"
		if(itemcopy.owner == self.key):
			itemcopy.return_item()
			itemcopy.put()
			return "Item successfully returned to your library"
		elif (itemcopy.borrower == self.key):
			notification = ConfirmReturn(useraccount=itemcopy.owner,item=itemcopy.key)
			notification.put()
			return "Notice sent to owner, awaiting their confirmantion"
		else:
			return "You are not the owner of this item, nor are you borrowing it"

	def change_due_date(self, itemCopyID, newDueDate):
		"""Update the date that a item is due

		Arguments:
		itemCopyID: an ID representing a ItemCopy object, the item to be returned
		newDueDate: a string representing the new due date of the item

		Return Value:
		A message describing the success or failure or the operation
		"""
		from src.items.models import ItemCopy
		from src.activity.models import DueDateExtension
		itemcopy = ItemCopy.get_by_id(int(itemCopyID))
		new_date = datetime.datetime.strptime(newDueDate, '%Y-%m-%d')

		if(itemcopy == None):
			return "Invalid item ID"
		if(itemcopy.owner == self.key):
			itemcopy.update_due_date(new_date)
			itemcopy.put()
			return "Due date successfully updated"
		elif (itemcopy.borrower == self.key):
			import datetime
			notification = DueDateExtension(useraccount=itemcopy.owner,item=itemcopy.key,due_date=new_date)
			notification.put()
			return "Request sent to owner"
		else:
			return "You are not the owner of this item, nor are you borrowing it"


class Anonymous(AnonymousUser):
	name = u"Anonymous"
