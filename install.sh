#!/bin/sh

# jamorham - run with sh ./install.sh

echo

if [ "DEVSHELL_PROJECT_ID" = "" ]
then
echo "This script should be run from within Google Cloud Shell from the Google Developers Console"
exit
fi

if [ ! -f app.yaml ]
then
echo "ERROR: Please change in to the project directory and then run: sh ./install.sh"
exit
fi

echo "This will install the Parakeet Receiver to: $DEVSHELL_PROJECT_ID"
echo
echo -n "Type: y or Y to continue, any other key to exit: "
read y
echo

if [ "$y" != "Y" ] && [ "$y" != "y" ]
then
echo "Cancelling install!"
exit
fi

rm -f app.yaml.tmp 2>/dev/null
grep -v -e ^version: -v -e ^application: app.yaml >app.yaml.tmp
rm -f app.yaml 2>/dev/null
mv app.yaml.tmp app.yaml

if gcloud config set app/promote_by_default true
then
if gcloud preview app deploy ./app.yaml
then
echo
echo "INSTALL SUCCESS!"
echo
echo "Please visit the site ASAP and login to ensure you register yourself as the admin user"
echo
else
echo
echo "INSTALL FAILED!"
exit
fi
else
echo
echo "Failed to set promote by default option"
exit
fi
