#!/bin/bash

#RunENV_Check
if readlink /proc/$$/exe | grep -qs "dash"; then
	echo "This script needs to be run with bash, not sh"
	exit 1
fi

#Show Usage
Usage() {
	echo -e "\033[33m =^..^= Baidu Wenku Downloader =^..^=\n" \
			"Usage: [options]\n" \
			"Options:\n" \
			" -u Required: Please enter the document url you want to download.\n" \
			" -o Required: Output Filename.\n" \
			" -h Show Usage of this script. \033[0m"
}

Download(){
	echo "Start Downloading..."
	curl -s -L 'http://mywenkubao.com/moban.aspx' \
		-H 'Origin: http://mywenkubao.com' \
		-H 'Accept-Encoding: gzip, deflate' \
		-H 'Accept-Language: zh-CN,zh;q=0.8' \
		-H 'Upgrade-Insecure-Requests: 1' \
		-H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36' \
		-H 'Content-Type: application/x-www-form-urlencoded' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8' \
		-H 'Cache-Control: max-age=0' \
		-H 'Referer: http://mywenkubao.com/moban.aspx' \
		-H 'Connection: keep-alive' \
		-H 'DNT: 1' \
		--data "txtUrl=$DOCURL" \
		--compressed\
		-o $FILENAME
}

#Var_Set
if (($# == 0)); then
    Usage
    exit 0
fi

while getopts "u:o: h" opt; do
    case $opt in
		u)
			DOCURL=$OPTARG
			;;
		o)
			FILENAME=$OPTARG
			Download
			exit 0
			;;
		h)
			Usage
			exit 0
			;;

        \?)
#            echo "Invalid option: -$OPTARG" >&2
            exit 1
            ;;
        :)
            echo "Option -$OPTARG requires an argument." >&2
            exit 1
            ;;
    esac
done
