# Views
from google.appengine.api import users
from flask import jsonify, render_template, request, url_for, redirect
from src.items.models import Item,ItemCopy
from activity.models import RequestToBorrow, WaitingToBorrow
import logging
from decorators import crossdomain
from src import app
from utilities.JsonIterable import *
from accounts import login as login_account, logout as logout_account, join as join_account, delete as delete_account, current_user
from accounts.models import UserAccount
from activity.models import Action
from google.appengine.api import mail
from datetime import date,timedelta,datetime
import re
import filters

#mail = Mail(app)

def warmup():
	# https://developers.google.com/appengine/docs/python/config/appconfig#Warmup_Requests
	# This function loads the views into the new instance when
	# one has to start up due to load increases on the app
	return ''

#return (datetime.now() - self.last_update) > timedelta(minutes=1000)

@app.route("/tasks/item_due_reminders")
def item_due_reminders():
	count = 0
	"""find all the items due tomorrow and send reminder emails"""
	items = ItemCopy.query(ItemCopy.due_date==date.today() + timedelta(days=1)).fetch()
	for item in items:
		count += 1
		owner = UserAccount.query(UserAccount.key==item.owner).get()
		mail.send_mail(sender=owner.email,
			to=UserAccount.query(UserAccount.key==item.borrower).get().email,
			subject="Item Due Soon",
			body="""The following item is due to be returned tomorrow: '%s'.
			
Please return it to %s"""%(Item.query(Item.key==item.item).get().title,owner.name))
	return "%s reminders were sent out" %count

@app.route("/post_issue", methods=['POST'])
def post_issue():
	if request.method == 'POST' and "submitterName" in request.form and "submitterEmail" in request.form and "issueName" in request.form and "issueDescription" in request.form:
		title = request.form["issueName"]
		body = "Submitter Name: " + request.form["submitterName"] + "\nSubmitter Email: " + request.form["submitterEmail"] + "\nDescription:\n" + request.form["issueDescription"]
		labels = request.form["issueType"]
		import requests
		import json
		auth = ("sharingcommonsbot", "Sh4r3B0t")
		github_url = "https://api.github.com"
		headers = {'Content-Type': 'application/json'}
		repo_owner = "natecarrier"
		repo = "sharingcommons"
		issues_url = "{0}/{1}".format(github_url, "/".join(
				["repos", repo_owner, repo, "issues"]))
		data = {"title": title,
				"body": body,
				"labels": labels}
		result = requests.post(issues_url,
							 auth=auth,
							 headers=headers,
							 data=json.dumps(data))
	return jsonify({"result": str(result.status_code)})

@app.route("/update_user", methods=['POST'])
def update_user():
	if request.method == 'POST':
		# Get all attributes from form (or user if not in form)
		user = current_user()
		if "displayName" in request.form:
			name = request.form["displayName"]
		else:
			name = user.name
		if "lendingLength" in request.form :
			length = request.form["lendingLength"]
		else:
			length = user.lending_length
		if "customURL" in request.form:
			custom_url = request.form["customURL"]
		else:
			custom_url = user.custom_url
		if "profilePrivacy" in request.form:
			profile_privacy = int(request.form["profilePrivacy"])
		else:
			profile_privacy = user.profile_privacy
		if "bookPrivacy" in request.form:
			book_privacy = int(request.form["bookPrivacy"])
		else:
			book_privacy = user.book_privacy
		if "moviePrivacy" in request.form:
			movie_privacy = int(request.form["moviePrivacy"])
		else:
			movie_privacy = user.movie_privacy
		if "publicInfo" in request.form:
			public_info = request.form["publicInfo"]
		else:
			public_info = user.public_info
		if "additionalInfo" in request.form:
			info = request.form["additionalInfo"]
		else:
			info = user.info
		# Update user object
		if user.update(name,length,custom_url,profile_privacy,book_privacy,movie_privacy,public_info,info):
			return jsonify({"result": "success"})
		else:
			return jsonify({"result": "url in use"})
	
@app.route("/crossdomain")
@crossdomain(origin='*')
def test_view():
	"""test view for checking accessibility of cross-domain ajax requests
	
	"""
	return "this is a response"

def render_response(template, *args, **kwargs):
	"""helper function for adding variables for the template processor
	
	"""
	return render_template(template, *args, user=current_user(), **kwargs)

################################ Website landing pages ##################################
def index():

	# Each user has an invitation link (in /network) which they send to other users to
	# invite them to connect. Currently, this is the only method of connecting
	# users. The link adds an argument to the index link (?connect=) with the inviter's
	# user ID. A modal appears in the view if otherUserID is not 0.
	
	# Grab User ID from connection invitation
	otherUserID = request.args.get('connect')
	
	# If no connect argument is present (just a regular visit to the dashboard), set to 0 (ignored in view)
	if otherUserID is None:
		connectionType = 0 #No connection request is being made
		otherUserID = 0
		otherUserName = 0
	else:
		# Get User Name from User ID
		otherUserObj = UserAccount.get_by_id(int(otherUserID))
		# Set invalid objects to invalid
		if otherUserObj is None:
			otherUserID = 0
			otherUserName = 0
			connectionType = 1 #Invalid User ID
		else:
			otherUserName = otherUserObj.name
			connectionType = 2 #Valid User
	
		# Don't let a user connect with him/herself, set to 0 so they get nothing
		if int(otherUserID) == current_user().get_id():
			connectionType = 3 #Own self
			
		# Don't let a user connect with an existing connection
		#if otherUserObj in current_user().connected_accounts:
		#	connectionType = 4 #Existing Connection
			
	return render_response('home.html',connectUserID=otherUserID,connectUserName=otherUserName,connectType=connectionType)
	
def library():
	# Create a list of items (as dicts) within the user's library
	itemlist = []
	useraccount = current_user()
	for copy in useraccount.get_library():
		item = Item.query(Item.key == copy.item).get().to_dict()
		item["item_subtype"] = copy.item_subtype
		if copy.star_rating:
			item["star_rating"] = copy.star_rating
		else:
			item["star_rating"] = 0
		item["escapedtitle"] = re.escape(item["title"])
		if copy.borrower is None:
			item["available"] = True
		else:
			item["available"] = False
		itemlist.append(item)
	# Sort itemlist alphabetically, with title as the primary sort key,
	# author as secondary, and item_subtype as tertiary
	itemlist.sort(key=lambda item: item["item_subtype"])
	itemlist.sort(key=lambda item: item["title"].lower())
		
	return render_response('managelibrary.html', itemlist=itemlist)
	
def network():
	return render_response('network.html')
	
def discover():
	# Start by creating a list of items (as dicts) within the user's library
	# This is necessary prep to be able to show that the item is in the user's library
	librarylist = {}
	useraccount = current_user()
	for copy in useraccount.get_library():
		item = Item.query(Item.key == copy.item).get().to_dict()
		item["item_subtype"] = copy.item_subtype
		item["escapedtitle"] = re.escape(item["title"])
		librarylist[(item["item_key"],item["item_subtype"])] = item
	
	# Create a list of all items (as dicts) in the user's network
	user = current_user()
	itemlist = []
	for connection in user.get_connections():
		u = UserAccount.getuser(connection.id())
		for copy in u.get_library():
			item = Item.query(Item.key == copy.item).get().to_dict()
			item["item_subtype"] = copy.item_subtype
			item["escapedtitle"] = re.escape(item["title"])
			if copy.borrower is None:
				item["available"] = True
			else:
				item["available"] = False
			# Check to see if book is in the user's library
			item["inLibrary"] = []
			for item_subtype in ['book', 'ebook', 'audiobook']:
				if (item["item_key"],item_subtype) in librarylist:
					item["inLibrary"].append(item_subtype)
			itemlist.append(item)
	
	# Sort itemlist alphabetically, with title as the primary sort key,
	# author as secondary, and item_subtype as tertiary
	itemlist.sort(key=lambda item: item["item_subtype"])
	itemlist.sort(key=lambda item: item["title"].lower())
	
	#Remove duplicate books (dictionaries) from itemlist (list)
	dedupeditemlist = []
	for item in itemlist:
		if item not in dedupeditemlist:
			dedupeditemlist.append(item)
	
	return render_response('discover.html',itemlist=dedupeditemlist)
	
def search():
	itemlist = {}
	item_type = request.args.get('item_type')
	subtype_book = request.args.get('subtype_book')
	subtype_ebook = request.args.get('subtype_ebook')
	subtype_audiobook = request.args.get('subtype_audiobook')
	subtype_dvd = request.args.get('subtype_dvd')
	subtype_bluray = request.args.get('subtype_bluray')
	user_email = request.args.get('user_email')
	searchterm = request.args.get('query')
	attr = request.args.get('refineSearch')
	src = request.args.get('src')
	
	# If searching for a user, redirect to profile
	if user_email:
		profile_user = UserAccount.query(UserAccount.email==searchterm).get()
		if not profile_user:
			return redirect(url_for("invalid_profile"))
		else:
			if profile_user.custom_url:
				return redirect('/user/' + profile_user.custom_url)
			else:
				return redirect('/user/' + str(profile_user.get_id()))
	
	subtype_specified = "true" # Used in javascript to determine whether out-of-network cookie should be respected or not
	
	if item_type is None and subtype_book is None and subtype_ebook is None and subtype_audiobook is None and subtype_dvd is None and subtype_bluray is None:
		#Nothing was specified, so act as if they searched books
		item_type = "book"
	
	if subtype_book or subtype_ebook or subtype_audiobook or subtype_dvd or subtype_bluray:
		# If subtype is included, item_type may not be, so it must be added
		if subtype_book or subtype_ebook or subtype_audiobook:
			item_type = "book"
		if subtype_dvd or subtype_bluray:
			item_type = "movie"
	else:
		# None are included, so only item_type is being pass; set all subtypes to true
		if item_type == "book":
			subtype_specified = "false"
			subtype_book = "true"
			subtype_ebook = "true"
			subtype_audiobook = "true"
		elif item_type == "movie":
			subtype_specified = "false"
			subtype_dvd = "true"
			subtype_bluray = "true"
			
	if attr == "all":
		attr = None
	
	if searchterm is None:
		searchterm = ""
	else:
		searchterm = searchterm.lstrip()
		
	if searchterm is None or searchterm == "":
		pass
	else:
		cur_user = current_user()
		logging.info(cur_user)
		if not cur_user.is_authenticated():
			#Assume no books in library or network, return results only
			itemlist = Item.search_by_attribute(item_type,searchterm,attr)
			for item in itemlist:
				item["inLibrary"] = []
				item["inNetwork"] = []
		
		else:
			user = current_user()
			
			#Create a dictionary of the user's items
			librarylist = {}
			for copy in user.get_library():
				copyItemKey = Item.query(Item.key == copy.item).get().item_key
				copyItemSubtype = copy.item_subtype
				librarylist[(copyItemKey,copyItemSubtype)] = copy.to_dict()
				
			#Create a dictionary of the items in the user's network
			#The dict, networkitemlist, includes each ItemCopy object, with it's associated item_key.
			networkitemlist = {}
			for connection in user.get_connections():
				u = UserAccount.getuser(connection.id())
				for copy in u.get_library():
					copyItemKey = Item.query(Item.key == copy.item).get().item_key
					copyItemSubtype = copy.item_subtype
					networkitemlist[(copyItemKey,copyItemSubtype)] = copy.to_dict()

			itemlist = Item.search_by_attribute(item_type,searchterm,attr)
			for item in itemlist:
				item["escapedtitle"] = re.escape(item["title"])
				
				# Check for copies in library and in network, 
				# return "inLibrary" list with all item types in Library
				# return "inNetwork" list with all item types in Library
				item["inLibrary"] = []
				item["inNetwork"] = []
				for item_subtype in ['book', 'ebook', 'audiobook', 'dvd', 'bluray']:
					if (item["item_key"],item_subtype) in librarylist:
						item["inLibrary"].append(item_subtype)
					if (item["item_key"],item_subtype) in networkitemlist:
						item["inNetwork"].append(item_subtype)
				
	return render_response('search.html', itemlist=itemlist, search=searchterm, attribute=attr, include_type=item_type, subtype_book=subtype_book, subtype_ebook=subtype_ebook, subtype_audiobook=subtype_audiobook, subtype_specified=subtype_specified, src=src)
	
def settings():
	return render_response('settings.html')
	
def tutorial():
	# First time login page, also available through the footer
	return render_response('tutorial.html')
	
def reportbug():
	return render_response('reportbug.html')
	
def about():
	return render_response('about.html')
	
def mobile_app():
	return render_response('mobileapp.html')
	
def licenses():
	return render_response('licenses.html')

def invalid_profile():
	return render_response('invalidprofile.html')
	
def profile(userID):
	try:
		int(userID)
		profile_user = UserAccount.get_by_id(int(userID))
		# Check if profile user has a custom url and forward if so
		if profile_user.custom_url:
			try:
				long(profile_user.custom_url) # Custom URLs MUST include at least one letter, so this will always fail with a custom URL
			except:
				return redirect('/user/' + profile_user.custom_url)
			
	except:
		# Query custom URLs
		custom_url_user = UserAccount.query(UserAccount.custom_url==userID).get()
		if custom_url_user:
			profile_user = custom_url_user
		else:
			return redirect(url_for("invalid_profile"))
	
	user = current_user()
	if user.is_authenticated():
		inNetwork = user.is_connected(profile_user)
	else:
		inNetwork = False
	if inNetwork or profile_user.profile_privacy == 1:
		if user == profile_user:
			inNetwork = True
		booklist = []
		for copy in profile_user.get_library():
			item = Item.query(Item.key == copy.item).get().to_dict()
			if item["item_type"] == "book":
				item["item_subtype"] = copy.item_subtype
				item["star_rating"] = copy.star_rating
				item["escapedtitle"] = re.escape(item["title"])
				if copy.borrower is None:
					item["available"] = True
				else:
					item["available"] = False
				item["copyID"] = copy.key.id()
				booklist.append(item)
			
		# Sort library alphabetically, with title as the primary sort key,
		# author as secondary, and item_subtype as tertiary
		booklist.sort(key=lambda item: item["item_subtype"])
		booklist.sort(key=lambda item: item["title"].lower())

		movielist = []
		for copy in profile_user.get_library():
			item = Item.query(Item.key == copy.item).get().to_dict()
			if item["item_type"] == "movie":
				item["item_subtype"] = copy.item_subtype
				item["star_rating"] = copy.star_rating
				item["escapedtitle"] = re.escape(item["title"])
				if copy.borrower is None:
					item["available"] = True
				else:
					item["available"] = False
				item["copyID"] = copy.key.id()
				movielist.append(item)
			
		# Sort library alphabetically, with title as the primary sort key,
		# author as secondary, and item_subtype as tertiary
		movielist.sort(key=lambda item: item["item_subtype"])
		movielist.sort(key=lambda item: item["title"].lower())
		import hashlib
		import urllib
		gravatar_url = "http://www.gravatar.com/avatar/" + hashlib.md5(profile_user.email).hexdigest() + "?s=150&d=" + urllib.quote(request.host_url,'') + "static%2Fimg%2Fnoimage.png"
		return render_response('profile.html',inNetwork=inNetwork,profile_user=profile_user,booklist=booklist,movielist=movielist,gravatar_url=gravatar_url)
	return redirect(url_for("invalid_profile"))
	
def generate_gravatar(userID,size):
	try:
		int(userID)
		user = UserAccount.get_by_id(int(userID))
		import hashlib
		import urllib
		gravatar_url = "http://www.gravatar.com/avatar/" + hashlib.md5(user.email).hexdigest() + "?s=" + size + "&d=" + urllib.quote(request.host_url,'') + "static%2Fimg%2Fnoimage.png"
	except:
		return False
	return redirect(gravatar_url)

def book_info(OLKey):
	# Pass book object to template
	itemBook = Item.get_by_key("book",OLKey)
	book = itemBook.to_dict()
	# Determine if the user owns this book
	# Find all connections who own this book and get the status for each
	# Find out any pending actions regarding this book
	# Find any current loans or borrow of this book
	
	# Check if user owns book and pass itemCopy object
	if current_user().is_authenticated():
		itemCopy = ItemCopy.query(ItemCopy.item==itemBook.key,ItemCopy.owner==current_user().key).fetch()
		if itemCopy:
			bookCopy = itemCopy[0]
		else:
			bookCopy = None
	else:
		bookCopy = None
	return render_response('itemdetail.html',item=book,itemCopy=bookCopy)
	
def movie_info(RTKey):
	itemMovie = Item.get_by_key("movie",RTKey)
	movie = itemMovie.to_dict()
	# Check if user owns book and pass itemCopy object
	if current_user().is_authenticated():
		itemCopy = ItemCopy.query(ItemCopy.item==itemMovie.key,ItemCopy.owner==current_user().key).fetch()
		if itemCopy:
			movieCopy = itemCopy[0]
		else:
			movieCopy = None
	else:
		movieCopy = None
	return render_response('itemdetail.html', item=movie, itemCopy=movieCopy)
	
def join():
	return render_response('join.html')

def handle_join():
	g_user = users.get_current_user()
	if g_user:
		if join_account(g_user):
			return redirect(url_for("tutorial"))
		else:
			return redirect(url_for("login"))
	return redirect(users.create_login_url(request.url))

def login():
	g_user = users.get_current_user()
	if g_user:
		if login_account(g_user):
			return redirect(request.args.get("next") or url_for("index"))
		else:
			return render_response('join.html',invalid_login=True)
	return redirect(users.create_login_url(request.url))

def logout():
	# Logs out User
	logout_account()
	return redirect(users.create_logout_url("/"))

######################## Internal calls (to be called by ajax) ##########################

def star_rating(item_subtype, item_key, star_rating):
	# Get Item
	# Infer item_type
	if item_subtype in ('book', 'ebook', 'audiobook'):
		item_type = 'book'
	elif item_subtype in ('dvd', 'bluray'):
		item_type = 'movie'
	else:
		item_type = ''
	item = Item.get_by_key(item_type,item_key)
	
	# Get ItemCopy
	itemCopy = ItemCopy.query(ItemCopy.item==item.key,ItemCopy.owner==current_user().key,ItemCopy.item_subtype==item_subtype).get()
	if itemCopy.update_star_rating(star_rating):
		return jsonify({"result":"success"})
	else:
		return jsonify({"result":"error"})

def delete_user():
	cur_user = current_user()
	if not cur_user:
		logging.info("there is not a user logged in")
		#return "<a href='%s' >Login</a>" %users.create_login_url(dest_url=url_for('library_requests',ISBN=ISBN))
	if delete_account(cur_user):
		return "Success"
	return ""

def library_requests(item_subtype, item_key):
	# Infer item_type
	if item_subtype in ('book', 'ebook', 'audiobook'):
		item_type = 'book'
	elif item_subtype in ('dvd', 'bluray'):
		item_type = 'movie'
	else:
		item_type = ''
	cur_user = current_user()
	if not cur_user:
		logging.info("there is not a user logged in")
		#return "<a href='%s' >Login</a>" %users.create_login_url(dest_url=url_for('library_requests',ISBN=ISBN))
		
	if request.method == 'GET':
		#check the database to see if the item is in the user's library
		item = Item.get_by_key(item_type,item_key)
		if item:
			if cur_user.get_book(item_subtype,item):
				return item.title
			else:
				return "You do not have this item in your library"
		else:
			return "This item was not found"
	elif request.method == 'POST':
		#add the item to the user's library
		#If not found, add it to the cache, then to the user's library
		item = Item.get_by_key(item_type,item_key)

		if not item:
			return "Item " + item_key + " was not found"
		else:
			if cur_user.get_item(item_subtype,item):
				return "This item is already in your library"
			cur_user.add_item(item_subtype, item)
			return "Item " + item_key + " was added to your library"
	elif request.method == 'DELETE':	
		#remove the item from the user's library
		item = Item.get_by_key(item_type,item_key)
		if not item:
			return "Item not found"
		else:
			if cur_user.get_item(item_subtype,item):
				cur_user.remove_item(item_subtype,item)
			return "Successfully deleted " + item_key + " from your library"
	else:
		#this should never be reached
		return "Error: http request was invalid"

def get_my_item_list():
	cur_user = current_user()
	if not cur_user:
		logging.info("there is not a user logged in")
		return "<a href='%s' >Login</a>" %users.create_login_url(dest_url=url_for('manage_library'))

	items = {}
	counter = 0
	for copy in cur_user.get_library():
		item = Item.query(Item.key == copy.item).get()
		items[counter] = item.to_dict()
		counter += 1
	return jsonify(JsonIterable.dict_of_dict(items))

def search_for_book(value, attribute=None):
	# This is broken because search_books_by_attribute now returns a list of dicts
	books = Item.search_by_attribute("book",value,attribute)
	if len(books) == 0:
		return jsonify({"Message":"No books found"})
	else:
		return jsonify(JsonIterable.dict_of_dict(books))

def manage_connections(otherUserID = None):
	cur_user = current_user()

	if request.method == 'GET':
		connections = cur_user.get_all_connections()
		users = []
		result = "you have " + str(len(connections)) + " connections"
		for connection in connections:
			result += "<br>" + connection.name
			user = dict()
			user["name"] = connection.name
			user["email"] = connection.email
			#user["username"] = connection.username
			user["id"] = connection.get_id()
			users.append(user)
		return jsonify({"connectedUsers":users})
	elif request.method == 'POST':
		cur_user = current_user()
		otherUser = UserAccount.getuser(int(otherUserID))
		result = cur_user.send_invite(otherUser)
		if(result == 0):
			return jsonify({"Message":"Invitation successfully sent"})
		elif(result == 1):
			return jsonify({"Message":"Connection already existed"})
		elif(result == 2):
			return jsonify({"Message":"Cannot create a connection with yourself"})
	elif request.method == 'DELETE':
		cur_user = current_user()
		otherUser = UserAccount.getuser(int(otherUserID))
		if cur_user.remove_connection(otherUser):
			return jsonify({"Message":"Connection successfully deleted"})
		else:
			return jsonify({"Message":"Connection didn't existed"})
	else:
		#this should never be reached
		return jsonify({"Message":"Error: http request was invalid"})
		
def simple_add_connection(otherUserID):
	cur_user = current_user()
	otherUser = UserAccount.getuser(int(otherUserID))
	if cur_user.add_connection(otherUser):
		return jsonify({"Message":"Connection successfully created"})
	else:
		return jsonify({"Message":"Connection already existed"})

def lend_item(itemCopyID, borrowerID, due_date = None):
	cur_user = current_user()
	return cur_user.lend_item(int(itemCopyID), int(borrowerID), due_date)

def borrow_item(itemCopyID, lenderID, due_date = None):
	cur_user = current_user()
	return cur_user.borrow_item(int(itemCopyID), int(lenderID), due_date)

def get_lent_items():
	cur_user = current_user()
	lentItems = []
	for itemcopy in cur_user.get_lent_books():
		item = Item.get_by_id(itemcopy.item.id())
		borrower = UserAccount.get_by_id(itemcopy.borrower.id())
		itemInfo = dict()
		itemInfo["title"] = item.title
		itemInfo["author"] = item.author
		itemInfo["copyID"] = itemcopy.key.id()
		itemInfo["borrowerId"] = itemcopy.borrower.id()
		itemInfo["borrower"] = borrower.name
		itemInfo["due_date"] = str(itemcopy.due_date)
		if itemcopy.manual_borrower_name:
			itemInfo["manual_borrower_name"] = itemcopy.manual_borrower_name
			itemInfo["manual_borrower_email"] = itemcopy.manual_borrower_email
		lentItems.append(itemInfo)
	return jsonify({"lentItems":lentItems})

def get_borrowed_items():
	cur_user = current_user()
	borrowedItems = []
	for itemcopy in cur_user.get_borrowed_books():
		if not itemcopy.manual_borrower_name: #Don't include items the user is manually lending (they would come up because the borrower is set to the user)
			item = Item.get_by_id(itemcopy.item.id())
			owner = UserAccount.get_by_id(itemcopy.owner.id())
			itemInfo = dict()
			itemInfo["title"] = item.title
			itemInfo["author"] = item.author
			itemInfo["copyID"] = itemcopy.key.id()
			itemInfo["ownerId"] = itemcopy.owner.id()
			itemInfo["owner"] = owner.name
			itemInfo["due_date"] = str(itemcopy.due_date)
			borrowedItems.append(itemInfo)
	return jsonify({"borrowedItems":borrowedItems})

def return_item(itemCopyID):
	cur_user = current_user()
	result = cur_user.return_item(itemCopyID)
	return jsonify({"Message":result})

def change_due_date(itemCopyID, newDueDate):
	cur_user = current_user()
	result = cur_user.change_due_date(itemCopyID, newDueDate)
	return jsonify({"Message":result})	
	
def search_network(item_key):
	user = current_user()

	networkuserlist = {}
	for connection in user.get_connections():
		u = UserAccount.getuser(connection.id())
		for copy in u.get_library():
			if Item.query(Item.key == copy.item).get().item_key == item_key:
				user = {}
				user["username"] = u.name
				user["itemCopyID"] = copy.key.id()
				if copy.borrower == None:
					user["available"] = "True"
				else:
					user["available"] = "False"
				networkuserlist[u.get_id()] = user

	return jsonify(networkuserlist)
	
def setup_item_borrow_actions(lenderID, itemCopyID):
	borrower = current_user()
	lender = UserAccount.getuser(int(lenderID))
	itemCopy = ItemCopy.get_by_id(int(itemCopyID))
	
	rtb1 = RequestToBorrow()
	rtb1.useraccount = lender.key
	rtb1.connection = borrower.key
	rtb1.item = itemCopy.key
	rtb1.put()
	
	wtb1 = WaitingToBorrow()
	wtb1.useraccount = borrower.key
	wtb1.connection = lender.key
	wtb1.item = itemCopy.key
	wtb1.put()
	return jsonify({"Message":"OK"})


def get_notifications():
	cur_user = current_user()
	notifications = []
	for notification in cur_user.pending_actions:
		info = dict()
		info["ID"] = notification.key.id()
		info["text"] = notification.text
		info["confirm_text"] = notification.accept_text
		info["confirm_activated"] = notification.can_accept
		info["reject_text"] = notification.reject_text
		info["reject_activated"] = notification.can_reject
		notifications.append(info)
	return jsonify({"notifications": notifications})

def confirm_notification(notificationID):
	action = Action.get_by_id(int(notificationID))
	result = action.confirm()
	return result

def reject_notification(notificationID):
	action = Action.get_by_id(int(notificationID))
	result = action.reject()
	return result
	
def get_user_email(userID):
	userEmail = UserAccount.get_by_id(int(userID)).email
	emailSplit = userEmail.split("@", 1)
	privacyEmail = userEmail[0:1] + '******@' + emailSplit[1]
	return jsonify({"email": privacyEmail})
	
def request_to_borrow(lenderID, itemCopyID):
	emailText = []
	emailText.append("You have received the following message from " + current_user().name + ", a Sharing Commons user.\n----\n\n")
	emailText.append(request.data)
	emailText.append("\n\n----\nReply to this message to send an email to " + current_user().name + " and set up the exchange. Once you've lent the item, visit beta.sharingcommons.com to confirm lending the item. "  + current_user().name + " will receive an email when the item is due")
	emailBody = ''.join(emailText)
	
	# Request item
	try:
		borrower = current_user()
		lender = UserAccount.getuser(int(lenderID))
		itemCopy = ItemCopy.get_by_id(int(itemCopyID))
		
		rtb1 = RequestToBorrow()
		rtb1.useraccount = lender.key
		rtb1.connection = borrower.key
		rtb1.item = itemCopy.key
		rtb1.put()
		
		wtb1 = WaitingToBorrow()
		wtb1.useraccount = borrower.key
		wtb1.connection = lender.key
		wtb1.item = itemCopy.key
		wtb1.put()
		
	except:
		return jsonify({"result":"error"})
	
	# Send email
	mail.send_mail(sender="Sharing Commons <admin@sharingcommons.com>",
			to=lender.name + " <" + lender.email + ">",
			reply_to=borrower.name + " <" + borrower.email + ">",
			subject='Sharing Commons: Request to Borrow "' + Item.query(Item.key == itemCopy.item).get().title + '"',
			body=emailBody)
	return jsonify({"result":"success"})
	
def manual_checkout(itemCopyID):
	if request.method == 'POST':
		itemCopy = ItemCopy.get_by_id(int(itemCopyID))
		
		# Manually checkout
		itemCopy.borrower = current_user().key
		itemCopy.lender = current_user().key
		itemCopy.manual_borrower_name = request.form["borrowerName"]
		if "borrowerEmail" in request.form:
			itemCopy.manual_borrower_email = request.form["borrowerEmail"]
		itemCopy.due_date = datetime.strptime(request.form["dueDate"], "%m/%d/%Y")
		itemCopy.put()
		
		return jsonify({"result":"success"})
	else:
		return jsonify({"result":"error"})
		
def send_invitation_request():
	if current_user().is_authenticated():
		if request.method == 'POST':
			import json
			jsonString = request.data
			jsonData = json.loads(jsonString)
			
			# Check email address
			if not mail.is_email_valid(jsonData["emailTo"]):
				return jsonify({"result":"invalidemail"})
			# Send email
			mail.send_mail(sender="Sharing Commons <admin@sharingcommons.com>",
						to=jsonData["emailTo"],
						reply_to=current_user().name + " <" + current_user().email + ">",
						subject=jsonData["emailSubject"],
						body=jsonData["emailBody"] + "\n\nJoin Sharing Commons and Connect with " + current_user().name + ": " + request.host_url + "?connect=" + str(current_user().get_id()),
						html=jsonData["emailBody"] + "<br><br>Join Sharing Commons and Connect with " + current_user().name + ":<br><br><a href='" + request.host_url + "?connect=" + str(current_user().get_id()) + "' style='display: block; background: #4E9CAF; padding: 5px; width: 180px; text-align: center; border-radius: 5px; color: white; font-weight: bold;'>Join Sharing Commons</button>")
			return jsonify({"result":"success"})
		